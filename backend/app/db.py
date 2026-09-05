"""SQLite 薄封装：检查任务、文档库、引擎配置。"""
import json
import sqlite3
from datetime import datetime
from typing import Any, Optional

from .config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS checks(
    id          TEXT PRIMARY KEY,
    title       TEXT,
    language    TEXT,
    word_count  INTEGER,
    status      TEXT,              -- queued/running/done/error
    options     TEXT,
    report      TEXT,              -- 完整报告 JSON（done 时）
    error       TEXT,
    created_at  TEXT,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS library_docs(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    word_count  INTEGER,
    is_builtin  INTEGER DEFAULT 0,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS engine_keys(
    key     TEXT PRIMARY KEY,
    api_key TEXT,
    enabled INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS crawl_jobs(
    id         TEXT PRIMARY KEY,
    source     TEXT,
    query      TEXT,
    target     INTEGER,
    fetched    INTEGER DEFAULT 0,
    added      INTEGER DEFAULT 0,
    status     TEXT,               -- running/stop_requested/stopped/done/error
    message    TEXT,
    created_at TEXT,
    updated_at TEXT
);
"""


def _migrate() -> None:
    with conn() as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(library_docs)")]
        if "origin" not in cols:
            c.execute("ALTER TABLE library_docs ADD COLUMN origin TEXT DEFAULT 'user'")
        if "source_url" not in cols:
            c.execute("ALTER TABLE library_docs ADD COLUMN source_url TEXT DEFAULT ''")
        ccols = [r[1] for r in c.execute("PRAGMA table_info(checks)")]
        if "doc_hash" not in ccols:
            c.execute("ALTER TABLE checks ADD COLUMN doc_hash TEXT")
        if "params_hash" not in ccols:
            c.execute("ALTER TABLE checks ADD COLUMN params_hash TEXT")
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_checks_dedup"
            " ON checks(doc_hash, params_hash, finished_at)"
        )


def purge_old_checks(days: int) -> int:
    """删除 created_at 早于 N 天的检测记录（保留期清理），返回删除行数。"""
    with conn() as c:
        cur = c.execute(
            "DELETE FROM checks WHERE created_at < datetime('now', ?)",
            (f"-{int(days)} day",),
        )
        return cur.rowcount


def find_check_by_hash(doc_hash: str, params_hash: str) -> Optional[sqlite3.Row]:
    """同文档 + 同参数的最近一次完成检测（提交去重用）。"""
    with conn() as c:
        return c.execute(
            "SELECT id, title, finished_at FROM checks"
            " WHERE doc_hash=? AND params_hash=? AND status='done'"
            " ORDER BY finished_at DESC LIMIT 1",
            (doc_hash, params_hash),
        ).fetchone()


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db() -> None:
    with conn() as c:
        c.executescript(_SCHEMA)
    _migrate()


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- checks ----------
def create_check(check_id: str, title: str, options: dict,
                 doc_hash: str = "", params_hash: str = "") -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO checks(id,title,status,options,doc_hash,params_hash,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (check_id, title, "queued", json.dumps(options, ensure_ascii=False),
             doc_hash, params_hash, now()),
        )


def update_check(check_id: str, **fields: Any) -> None:
    if not fields:
        return
    sets = ",".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE checks SET {sets} WHERE id=?", (*fields.values(), check_id))


def get_check(check_id: str) -> Optional[sqlite3.Row]:
    with conn() as c:
        return c.execute("SELECT * FROM checks WHERE id=?", (check_id,)).fetchone()


def list_checks() -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute(
            "SELECT id,title,language,word_count,status,created_at FROM checks"
            " ORDER BY created_at DESC"
        ).fetchall()


def delete_check(check_id: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM checks WHERE id=?", (check_id,))


# ---------- library ----------
def add_doc(title: str, content: str, word_count: int, is_builtin: bool = False,
            origin: str = "user", source_url: str = "") -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO library_docs(title,content,word_count,is_builtin,origin,source_url,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (title, content, word_count, int(is_builtin), origin, source_url, now()),
        )
        return int(cur.lastrowid)


def doc_title_exists(title: str) -> bool:
    with conn() as c:
        return c.execute(
            "SELECT 1 FROM library_docs WHERE title=? LIMIT 1", (title,)
        ).fetchone() is not None


def get_doc_full(doc_id: int) -> Optional[sqlite3.Row]:
    with conn() as c:
        return c.execute(
            "SELECT id,title,content,word_count,is_builtin FROM library_docs WHERE id=?",
            (doc_id,),
        ).fetchone()


def list_docs() -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute(
            "SELECT id,title,word_count,is_builtin,created_at FROM library_docs"
            " ORDER BY is_builtin DESC, created_at DESC"
        ).fetchall()


def all_docs_full() -> list[sqlite3.Row]:
    """语料索引构建用，含全文。"""
    with conn() as c:
        return c.execute("SELECT id,title,content,word_count,is_builtin FROM library_docs").fetchall()


def delete_doc(doc_id: int) -> bool:
    with conn() as c:
        row = c.execute("SELECT is_builtin FROM library_docs WHERE id=?", (doc_id,)).fetchone()
        if not row or row["is_builtin"]:
            return False
        c.execute("DELETE FROM library_docs WHERE id=?", (doc_id,))
        return True


# ---------- crawl jobs ----------
def create_job(job_id: str, source: str, query: str, target: int) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO crawl_jobs(id,source,query,target,status,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (job_id, source, query, target, "running", now(), now()),
        )


def update_job(job_id: str, **fields: Any) -> None:
    fields["updated_at"] = now()
    sets = ",".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE crawl_jobs SET {sets} WHERE id=?", (*fields.values(), job_id))


def get_job(job_id: str) -> Optional[sqlite3.Row]:
    with conn() as c:
        return c.execute("SELECT * FROM crawl_jobs WHERE id=?", (job_id,)).fetchone()


def list_jobs() -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute("SELECT * FROM crawl_jobs ORDER BY created_at DESC LIMIT 50").fetchall()


# ---------- engine keys ----------
def set_engine_key(key: str, api_key: str, enabled: bool) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO engine_keys(key,api_key,enabled) VALUES(?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET api_key=excluded.api_key, enabled=excluded.enabled",
            (key, api_key, int(enabled)),
        )


def get_engine_keys() -> dict[str, dict]:
    with conn() as c:
        rows = c.execute("SELECT * FROM engine_keys").fetchall()
    return {
        r["key"]: {"api_key": r["api_key"], "enabled": bool(r["enabled"])} for r in rows
    }
