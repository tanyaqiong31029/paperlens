"""SPA 静态路径穿越、无令牌轮询不计失败、重启收尾、JSON 请求体校验与采集名额回归测试。"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import _auth_bans, _auth_failures, _spa_file, app
from app.services import crawler


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ---------------- SPA 兜底路由：路径穿越 ----------------
@pytest.fixture()
def dist(tmp_path):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<html>index</html>", encoding="utf-8")
    (d / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "secret.db").write_text("top secret", encoding="utf-8")
    return d


def test_spa_serves_real_file_inside_dist(dist):
    assert _spa_file(dist, "favicon.svg") == (dist / "favicon.svg").resolve()
    assert _spa_file(dist, "") == (dist / "index.html").resolve()
    assert _spa_file(dist, "report/abc") == (dist / "index.html").resolve()


@pytest.mark.parametrize(
    "path",
    [
        "../secret.db",  # /..%2Fsecret.db 解码后
        "assets/../../secret.db",
        "/etc/passwd",  # GET //etc/passwd → path="/etc/passwd"，dist / "/etc/passwd" 会丢弃 dist
        "SECRET_ABS",  # 占位：替换为 secret.db 的绝对路径
        "assets",  # 目录不是文件
    ],
)
def test_spa_rejects_paths_outside_dist(dist, path):
    if path == "SECRET_ABS":
        path = str((dist.parent / "secret.db").resolve())
    assert _spa_file(dist, path) == (dist / "index.html").resolve()


# ---------------- 令牌：无令牌请求不计失败 ----------------
def test_missing_token_does_not_count_as_failure(client, monkeypatch):
    """未携带 X-Admin-Token 的轮询只回 401，不会把 IP 封禁（用户还没机会输令牌）。"""
    monkeypatch.setattr(config, "ADMIN_TOKEN", "tok-secret")
    _auth_failures.clear()
    _auth_bans.clear()
    try:
        for _ in range(config.AUTH_FAIL_LIMIT * 3):
            r = client.get("/api/crawl/jobs")
            assert r.status_code == 401
        assert not _auth_bans
        assert not _auth_failures
        # 输入正确令牌后立即可用
        r = client.get("/api/crawl/jobs", headers={"X-Admin-Token": "tok-secret"})
        assert r.status_code == 200
    finally:
        _auth_failures.clear()
        _auth_bans.clear()


def test_wrong_token_still_counts(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "tok-secret")
    _auth_failures.clear()
    _auth_bans.clear()
    try:
        r = client.get("/api/crawl/jobs", headers={"X-Admin-Token": "nope"})
        assert r.status_code == 401
        assert sum(len(v) for v in _auth_failures.values()) == 1
    finally:
        _auth_failures.clear()
        _auth_bans.clear()


# ---------------- 启动收尾：遗留的非终态任务 ----------------
def test_recover_interrupted_marks_stale_rows():
    ids = {s: f"rec-{s}-{uuid.uuid4().hex[:6]}" for s in ("queued", "running", "done")}
    for status, cid in ids.items():
        db.create_check(cid, "t", {})
        db.update_check(cid, status=status)
    jids = {s: f"job-{s}-{uuid.uuid4().hex[:6]}" for s in ("running", "stop_requested", "done")}
    for status, jid in jids.items():
        db.create_job(jid, "arxiv", "", 20)
        db.update_job(jid, status=status)

    n_checks, n_jobs = db.recover_interrupted()
    assert n_checks >= 2 and n_jobs >= 2

    def check_status(cid):
        row = db.get_check(cid)
        assert row is not None
        return row["status"]

    def job_status(jid):
        row = db.get_job(jid)
        assert row is not None
        return row["status"]

    assert check_status(ids["queued"]) == "error"
    assert check_status(ids["running"]) == "error"
    assert check_status(ids["done"]) == "done"
    row = db.get_check(ids["running"])
    assert row is not None and row["error"] and row["finished_at"]
    assert job_status(jids["running"]) == "error"
    assert job_status(jids["stop_requested"]) == "error"
    assert job_status(jids["done"]) == "done"


# ---------------- JSON 请求体：非对象 / 非整数 target → 400 ----------------
@pytest.mark.parametrize(
    "payload",
    [
        [],
        "str",
        123,
        None,
        {"source": "arxiv", "target": None},
        {"source": "arxiv", "target": "abc"},
        {"source": "arxiv", "target": [1]},
        {"source": "arxiv", "target": True},
    ],
)
def test_crawl_bad_body_is_400(client, payload):
    r = client.post("/api/crawl/jobs", json=payload)
    assert r.status_code == 400, r.text


def test_crawl_invalid_json_is_400(client):
    r = client.post(
        "/api/crawl/jobs", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 400


@pytest.mark.parametrize("payload", [[], "str", None, 1])
def test_reduce_non_object_body_is_400(client, payload):
    r = client.post("/api/reduce", json=payload)
    assert r.status_code == 400, r.text


# ---------------- 采集：名额释放与标题截断去重 ----------------
def test_start_job_releases_slot_on_failure(monkeypatch):
    before = crawler._active_jobs

    def boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(crawler.db, "create_job", boom)
    for _ in range(crawler.MAX_CONCURRENT_CRAWLS + 1):
        with pytest.raises(RuntimeError, match="db down"):
            crawler.start_job("arxiv", "", 20)
    assert crawler._active_jobs == before


def test_crawl_dedup_uses_truncated_title(monkeypatch):
    long_title = "长标题" * 100 + uuid.uuid4().hex  # > 200 字符
    docs = [
        {"title": long_title, "content": "内容" * 30, "origin": "arxiv", "url": ""}
        for _ in range(2)
    ]
    monkeypatch.setitem(crawler._ADAPTERS, "arxiv", lambda q, t, stop, errs: iter(docs))
    monkeypatch.setattr(crawler.CORPUS, "add_and_index", lambda _did: None)

    jid = f"dedup-{uuid.uuid4().hex[:6]}"
    db.create_job(jid, "arxiv", "", 20)
    with crawler._jobs_lock:
        crawler._active_jobs += 1  # _run_job 结束时会归还
    crawler._run_job(jid)

    job = db.get_job(jid)
    assert job is not None
    assert job["fetched"] == 2
    assert job["added"] == 1  # 第二篇因截断后标题相同被去重
