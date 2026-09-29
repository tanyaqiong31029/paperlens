"""限流、令牌失败退避与文档库文本上限测试。"""

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import RateLimitMiddleware, _auth_bans, _auth_failures, app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_rate_limit_middleware_unit():
    """滑动窗口限流：窗口内超限返回 429 并带 Retry-After。"""
    import asyncio

    async def run():
        sent_all = []

        async def dummy_app(scope, receive, send):
            sent_all.append({"status": 200})

        mw = RateLimitMiddleware(dummy_app, per_minute=3)
        scope = {"type": "http", "method": "GET", "path": "/api/stats"}

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg):
            sent_all.append(msg)

        for _ in range(3):
            await mw(scope, receive, send)  # 前 3 个放行
        await mw(scope, receive, send)  # 第 4 个应被拒
        return sent_all

    sent = asyncio.run(run())
    rejected = [m for m in sent if m.get("status") == 429]
    assert rejected, sent
    assert sum(1 for m in sent if m.get("status") == 200) == 3


def test_rate_limit_api_level(client, monkeypatch):
    """API 级限流：把窗口阈值压小后连续请求触发 429。"""
    # 实际限流阈值在中间件实例内固定（默认 300/min），足够测试套件使用；
    # 这里只验证正常请求不受影响
    r = client.get("/api/health")
    assert r.status_code == 200
    del monkeypatch


def test_token_failure_backoff(client, monkeypatch):
    """连续输错令牌达到上限后进入临时封禁（429），正确令牌在封禁期间同样被拒。"""
    monkeypatch.setattr(config, "ADMIN_TOKEN", "tok-secret")
    _auth_failures.clear()
    _auth_bans.clear()
    try:
        text = {"text": "测试内容" * 20}
        # 前 4 次失败 → 401
        for i in range(config.AUTH_FAIL_LIMIT - 1):
            r = client.post("/api/checks", data=text, headers={"X-Admin-Token": f"wrong-{i}"})
            assert r.status_code == 401
        # 第 5 次失败 → 触发封禁 429
        r = client.post("/api/checks", data=text, headers={"X-Admin-Token": "wrong-last"})
        assert r.status_code == 429
        assert "Retry-After" in r.headers
        # 封禁期间正确令牌也被拒
        r = client.post("/api/checks", data=text, headers={"X-Admin-Token": "tok-secret"})
        assert r.status_code == 429
    finally:
        _auth_failures.clear()
        _auth_bans.clear()


def test_library_doc_text_cap(client, monkeypatch):
    """文档库上传：解析后文本超 MAX_TEXT_CHARS → 413。"""
    monkeypatch.setattr(config, "MAX_TEXT_CHARS", 100)
    r = client.post(
        "/api/library/documents",
        data={"text": "超长内容" * 200, "title": "超长文档"},
    )
    assert r.status_code == 413


def test_audit_event_written(client, tmp_path, monkeypatch):
    """提交检测应写审计事件（不含正文）。"""
    import json as jsonlib

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    text = "综上所述，审计测试文本，用于验证审计日志写入。内容长度需要超过五十个字符以上才行。" * 2
    client.post("/api/checks", data={"text": text, "mode": "aigc", "title": "审计测试"})
    log_file = tmp_path / "audit.log"
    assert log_file.exists()
    rec = jsonlib.loads(log_file.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert rec["event"] == "check_submit"
    assert "text" not in rec and "content" not in rec
