"""API 冒烟测试：健康、统计、完整检测流程、降AIGC、管理令牌、错误输入。"""
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:   # with 语句触发 startup（种子语料 + 索引重建）
        yield c


def _wait_done(client, check_id, timeout=60):
    for _ in range(timeout // 2):
        data = client.get(f"/api/checks/{check_id}").json()
        if data["status"] in ("done", "error"):
            return data
        time.sleep(0.5)
    raise TimeoutError("检测超时")


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_stats_shape(client):
    s = client.get("/api/stats").json()
    assert {"corpus", "total_checks", "engines"} <= set(s)
    assert s["corpus"]["documents"] > 0


def test_full_check_flow(client):
    text = (
        "综上所述，社交媒体营销已经成为企业数字化转型的重要组成部分。"
        "研究表明，内容质量与互动频率对品牌传播效果具有重要影响，值得深入探讨。"
        "值得注意的是，短视频平台的兴起带来了新的机遇和挑战，企业应当构建全方位的营销体系。"
        "此外，直播电商进一步缩短了消费决策链条，实现品效合一。"
    )
    r = client.post("/api/checks", data={"text": text, "mode": "full", "title": "冒烟测试"})
    assert r.status_code == 200
    check_id = r.json()["check_id"]

    data = _wait_done(client, check_id)
    assert data["status"] == "done"
    assert data["report"]["plagiarism"] is not None
    local = data["report"]["aigc"]["local"]
    assert 0 <= local["rate"] <= 100
    engine_names = [e["name"] for e in data["report"]["aigc"]["engines"]]
    assert "本地集成引擎 v2" in engine_names
    # 实验性引擎必须在列表中且明确标注，不得有真实结果
    cl = next(e for e in data["report"]["aigc"]["engines"] if e["key"] == "copyleaks")
    assert cl["status"] == "experimental" and cl["rate"] is None


def test_too_short_text_rejected(client):
    assert client.post("/api/checks", data={"text": "太短"}).status_code == 400


def test_body_size_limit(client):
    # 伪造超大 content-length，应在读取正文前被拒
    r = client.post("/api/checks", data={"text": "正常内容" * 20},
                    headers={"content-length": str(config.MAX_BODY_BYTES + 1)})
    assert r.status_code == 413


def test_engines_list_marks_experimental(client):
    engines = client.get("/api/engines").json()
    by_key = {e["key"]: e for e in engines}
    assert by_key["copyleaks"]["experimental"] is True
    assert not by_key["copyleaks"]["enabled"]


def test_crawl_sources_offline(client):
    sources = client.get("/api/crawl/sources").json()
    assert {s["key"] for s in sources} >= {"arxiv", "openalex-zh", "doaj", "europepmc"}


def test_reduce_api(client):
    text = ("综上所述，该方法在多个数据集上具有重要意义。研究表明，所提方法效果显著，"
            "值得深入探讨其内在机理。此外，相关技术日趋完善，为后续研究奠定了坚实基础。")
    r = client.post("/api/reduce", json={"text": text, "mode": "humanize"})
    assert r.status_code == 200
    d = r.json()
    assert d["changed_count"] >= 1
    assert d["full_text"] != text


def test_admin_token_guard(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret-token")
    try:
        # 无令牌 → 401
        assert client.post("/api/checks", data={"text": "测试内容" * 20}).status_code == 401
        # 健康与统计不受限
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/stats").status_code == 200
        # 带令牌 → 通过
        ok = client.post("/api/checks", data={"text": "测试内容" * 20},
                         headers={"X-Admin-Token": "secret-token"})
        assert ok.status_code == 200
    finally:
        monkeypatch.setattr(config, "ADMIN_TOKEN", "")
