"""审计日志：写接口的关键事件追加到 data/audit.log（JSON 行）。

只记录事件类型、对象标识与哈希前缀，不记录论文正文与 API Key——
日志与数据库同处本机数据目录，安全域一致，但保持最小化原则。
"""
import json
import threading
import time

from .. import config

_lock = threading.Lock()


def log_event(event: str, **fields) -> None:
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event}
    for k, v in fields.items():
        if v is None:
            continue
        if k == "title":
            v = str(v)[:40]        # 标题截断，降低日志敏感度
        rec[k] = v
    try:
        with _lock:
            with open(config.DATA_DIR / "audit.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — 审计失败不阻塞主流程
        pass
