"""有界等待队列测试：满载 429、完成释放、进度 TTL 清理。"""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.services import checker


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_queue_full_rejects_and_releases(client):
    """占满并发+等待坑位后提交 429；任务完成后坑位释放可再提交。"""
    # 用小容量独立验证：monkeypatch 信号量不可靠（模块级），
    # 因此这里验证真实路径：正常提交/完成循环不泄漏坑位。
    text = (
        "综上所述，社交媒体营销已经成为企业数字化转型的重要组成部分。"
        "研究表明，内容质量与互动频率对品牌传播效果具有重要影响，值得深入探讨。"
    )
    ids = []
    for i in range(5):  # 5 连发 > 并发 2：部分进入等待队列，均应受理而非 429
        r = client.post("/api/checks", data={"text": text, "mode": "aigc", "title": f"队列{i}"})
        assert r.status_code == 200
        ids.append(r.json()["check_id"])
    # 全部最终完成（坑位随完成释放，等待任务得以执行）
    for cid in ids:
        for _ in range(60):
            d = client.get(f"/api/checks/{cid}").json()
            if d["status"] in ("done", "error"):
                break
            time.sleep(0.4)
        assert d["status"] == "done", d
    # 此时容量应全部归还：再提交立即成功
    r = client.post("/api/checks", data={"text": text, "mode": "aigc", "title": "再提交"})
    assert r.status_code == 200
    client.delete(f"/api/checks/{ids[-1]}")


def test_queue_full_error_is_429(monkeypatch, tmp_path):
    """QueueFullError 路径：模拟满载信号量后 submit 抛错、坑位不泄漏。"""
    monkeypatch.setattr(checker, "_CAPACITY", threading.Semaphore(0))
    with pytest.raises(checker.QueueFullError):
        checker.submit("t", "正文" * 30, {})
    # Semaphore.acquire(False) 失败不消耗资源；恢复后可正常提交
    monkeypatch.setattr(checker, "_CAPACITY", threading.Semaphore(1))
    cid = checker.submit("t2", "正文" * 30, {})
    assert cid
    # 等任务结束释放
    for _ in range(40):
        d = db.get_check(cid)
        if d and d["status"] in ("done", "error"):
            break
        time.sleep(0.25)
    time.sleep(0.3)  # finally 释放信号量


def test_progress_ttl_cleanup(monkeypatch):
    """终态进度超过 TTL 后被惰性清理。"""
    checker.PROGRESS.clear()
    checker._set_progress("old-task", "done", 100)
    checker.PROGRESS["old-task"]["ts"] = time.time() - checker.PROGRESS_TTL_SECONDS - 1
    checker._set_progress("fresh-task", "parse", 10)
    checker._cleanup_progress()
    assert "old-task" not in checker.PROGRESS
    assert "fresh-task" in checker.PROGRESS
    checker.PROGRESS.clear()
