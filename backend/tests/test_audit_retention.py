"""审计日志与报告保留期清理测试。"""

from app import config, db
from app.services import audit


def test_audit_log_written(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    audit.log_event(
        "check_submit",
        check_id="abc123",
        title="测试标题很长的内容会被截断" * 5,
        doc_hash="deadbeef" * 4,
        word_count=100,
    )
    lines = (tmp_path / "audit.log").read_text(encoding="utf-8").strip().splitlines()
    import json

    rec = json.loads(lines[-1])
    assert rec["event"] == "check_submit"
    assert rec["check_id"] == "abc123"
    assert len(rec["title"]) <= 40 + 3  # 标题截断
    assert rec["doc_hash"] == "deadbeef" * 4


def test_purge_old_checks(tmp_path):
    db.init_db()
    keep_id = "keep00000001"
    old_id = "old000000001"
    db.create_check(keep_id, "新建保留", {})
    db.create_check(old_id, "过期应删", {})
    db.update_check(old_id, status="done", created_at="2020-01-01 00:00:00")
    db.update_check(keep_id, status="done")

    removed = db.purge_old_checks(30)
    assert removed >= 1
    assert db.get_check(old_id) is None
    assert db.get_check(keep_id) is not None
