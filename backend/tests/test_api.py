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


def test_body_limit_middleware_unit():
    """中间件单测：小上限下超限请求在读满前被 413 拒绝（asyncio.run 驱动）。"""
    import asyncio
    from app.main import BodySizeLimitMiddleware

    async def run():
        mw = BodySizeLimitMiddleware(None, max_bytes=10)
        scope = {"type": "http", "method": "POST", "path": "/api/checks"}
        chunks = [b"a" * 8, b"b" * 8]  # 分块到达，累计 16 > 10

        async def receive():
            if chunks:
                return {"type": "http.request", "body": chunks.pop(0), "more_body": bool(chunks)}
            return {"type": "http.disconnect"}

        sent = []

        async def send(msg):
            sent.append(msg)

        await mw(scope, receive, send)
        return sent

    sent = asyncio.run(run())
    assert sent[0]["status"] == 413


def test_body_limit_middleware_api(client, monkeypatch):
    """API 级：覆盖所有上传/JSON 接口（以文档库上传为例），无 Content-Length 也可拦截。"""
    from app.main import app as fastapi_app
    mw = next(m for m in fastapi_app.user_middleware)  # 确认中间件已挂载
    big = "x" * (config.MAX_BODY_BYTES + 10)
    r = client.post("/api/library/documents", data={"text": big, "title": "超大"})
    assert r.status_code == 413


def test_e2e_admin_token_flow(client, monkeypatch):
    """模拟前端完整流程：无令牌 401 → 弹窗输入令牌 → 提交检测 → 读取报告 → 导出。

    对应前端行为：apiFetch 收到 401 广播 TokenDialog，用户输入后令牌写入
    sessionStorage，后续请求统一携带 X-Admin-Token 请求头（不再支持 query 传递）。
    """
    monkeypatch.setattr(config, "ADMIN_TOKEN", "tok-123")
    text = (
        "综上所述，社交媒体营销已经成为企业数字化转型的重要组成部分。"
        "研究表明，内容质量与互动频率对品牌传播效果具有重要影响，值得深入探讨。"
    )
    H = {"X-Admin-Token": "tok-123"}

    # 1) 未持令牌：提交与读报告都 401
    assert client.post("/api/checks", data={"text": text}).status_code == 401
    # 2) query-string 令牌不再被接受（防止令牌进入历史/代理日志/Referer）
    r = client.post("/api/checks", data={"text": text, "token": "tok-123"})
    assert r.status_code == 401
    # 3) 用户输入令牌后：提交检测
    cid = client.post("/api/checks", data={"text": text, "title": "令牌E2E"},
                      headers=H).json()["check_id"]
    # 4) 读取报告直至完成
    for _ in range(60):
        data = client.get(f"/api/checks/{cid}", headers=H).json()
        if data["status"] == "done":
            break
        time.sleep(0.5)
    assert data["status"] == "done"
    assert data["report"]["aigc"]["local"]["rate"] is not None
    # 5) 导出报告（对应前端 blob 下载）
    exp = client.get(f"/api/checks/{cid}/export", headers=H)
    assert exp.status_code == 200 and "text/html" in exp.headers["content-type"]
    # 6) 无令牌读报告仍 401
    assert client.get(f"/api/checks/{cid}").status_code == 401


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


def test_dedup_reuses_existing_report(client):
    text = (
        "综上所述，社交媒体营销已经成为企业数字化转型的重要组成部分。"
        "研究表明，内容质量与互动频率对品牌传播效果具有重要影响，值得深入探讨。"
        "值得注意的是，短视频平台的兴起带来了新的机遇和挑战。此外，直播电商进一步缩短了消费决策链条。"
    )
    r1 = client.post("/api/checks", data={"text": text, "mode": "full", "title": "去重A"})
    assert r1.status_code == 200 and r1.json()["deduplicated"] is False
    first = _wait_done(client, r1.json()["check_id"])
    assert first["status"] == "done"

    # 同文档 + 同参数 → 复用已有报告（0 计算）
    r2 = client.post("/api/checks", data={"text": text, "mode": "full", "title": "去重B"})
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2["deduplicated"] is True
    assert j2["check_id"] == r1.json()["check_id"]

    # 不同参数 → 正常新建任务
    r3 = client.post("/api/checks", data={"text": text, "mode": "plagiarism"})
    assert r3.json()["deduplicated"] is False
    assert r3.json()["check_id"] != r1.json()["check_id"]


def test_gzip_on_large_report(client):
    text = "综上所述，深度学习方法在多语种文本处理任务中表现出色。" * 40
    cid = client.post("/api/checks", data={"text": text, "mode": "aigc", "title": "gzip测试"}).json()["check_id"]
    _wait_done(client, cid)
    r = client.get(f"/api/checks/{cid}", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"


def test_sse_progress_stream(client):
    text = (
        "综上所述，社交媒体营销已经成为企业数字化转型的重要组成部分。"
        "研究表明，内容质量与互动频率对品牌传播效果具有重要影响，值得深入探讨。"
        "值得注意的是，短视频平台的兴起带来了新的机遇和挑战。此外，直播电商缩短了决策链条。"
    )
    cid = client.post("/api/checks", data={"text": text, "mode": "full", "title": "SSE测试"}).json()["check_id"]
    events = []
    with client.stream("GET", f"/api/checks/{cid}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data: ") or line.startswith("event: end"):
                events.append(line)
            if line.startswith("event: end"):
                break
    assert any('"status": "done"' in e for e in events), events[-3:]
    assert events[-1].startswith("event: end")


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
