"""检测任务编排：查重 + AIGC 多引擎，后台线程执行，DB 存状态与报告。

并发模型（有界队列）：
- 工作线程固定 2；提交时**先占坑**（信号量 = 2 并发 + N 等待位），
  满载直接拒绝（调用方返回 429），完成后释放——等待中的任务才有内存，
  无限积压不可能发生；
- 进度记录（PROGRESS）在任务终态（done/error）保留一段时间供 SSE 读取，
  由惰性 TTL 清理，防止进程内字典无限增长。
"""

import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from .. import config, db
from . import plagiarism, segmenter
from .aigc import engines as aigc_engines

# 有界工作线程池：并发检测数固定，避免每个请求各起一个线程
EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="paperlens-check")

MAX_RUNNING = 2  # 并发执行上限（与 EXECUTOR 一致）
MAX_WAITING = int(config.MAX_QUEUE_WAIT)  # 等待队列上限（默认 30）
_CAPACITY = threading.Semaphore(MAX_RUNNING + MAX_WAITING)

# 检测进度（进程内）：check_id -> {"stage": str, "pct": int, "ts": float}
# 终态后保留 PROGRESS_TTL_SECONDS 供 SSE 读取，过期由提交路径惰性清理
PROGRESS: dict[str, dict] = {}
PROGRESS_TTL_SECONDS = 180
_progress_lock = threading.Lock()


class QueueFullError(RuntimeError):
    """等待队列已满，调用方应返回 429。"""


def _set_progress(check_id: str, stage: str, pct: int) -> None:
    with _progress_lock:
        PROGRESS[check_id] = {"stage": stage, "pct": pct, "ts": time.time()}


def _cleanup_progress() -> None:
    """惰性清理：删除终态后超过 TTL 的进度记录（done/error 均含 ts）。"""
    now = time.time()
    with _progress_lock:
        stale = [
            cid for cid, p in PROGRESS.items() if now - p.get("ts", now) > PROGRESS_TTL_SECONDS
        ]
        for cid in stale:
            PROGRESS.pop(cid, None)


def submit(title: str, text: str, options: dict, doc_hash: str = "", params_hash: str = "") -> str:
    _cleanup_progress()
    # 接收任务前占坑：满载拒绝，防止批量提交无限积压耗尽内存
    if not _CAPACITY.acquire(blocking=False):
        raise QueueFullError(f"检测队列已满（并发 {MAX_RUNNING} + 等待 {MAX_WAITING}），请稍后再试")
    try:
        check_id = uuid.uuid4().hex[:12]
        db.create_check(check_id, title, options, doc_hash=doc_hash, params_hash=params_hash)
        EXECUTOR.submit(_run, check_id, text, options)
        return check_id
    except Exception:
        _CAPACITY.release()  # 入库失败则归还坑位
        raise


def _run(check_id: str, text: str, options: dict) -> None:
    try:
        try:
            db.update_check(check_id, status="running")
            _set_progress(check_id, "parse", 10)
            lang = segmenter.detect_language(text)
            db.update_check(
                check_id, language=lang, word_count=len(text.replace(" ", "").replace("\n", ""))
            )

            do_plag = options.get("mode", "full") in ("full", "plagiarism")
            do_aigc = options.get("mode", "full") in ("full", "aigc")

            plag_part = plagiarism.run(text, options) if do_plag else None

            # 联网全网核查：对本地未命中的可疑句做搜索引擎比对
            if plag_part is not None and options.get("web_check"):
                from . import webcheck

                try:
                    _set_progress(check_id, "web", 55)
                    plag_part["web"] = webcheck.run(plag_part["sent_results"], options)
                except Exception as e:  # noqa: BLE001
                    plag_part["web"] = {"status": "error", "note": f"联网核查异常：{e}"}

            _set_progress(check_id, "aigc", 70)
            aigc_part = aigc_engines.detect_all(text, lang) if do_aigc else None

            if plag_part is not None:
                db.update_check(check_id, title=_title_from(text, options.get("title", "")))

            _set_progress(check_id, "save", 92)
            report = {
                "plagiarism": plag_part,
                "aigc": {
                    "engines": aigc_part,
                    "local": _local_summary(aigc_part) if aigc_part else None,
                }
                if aigc_part
                else None,
                "options": options,
            }
            db.update_check(
                check_id,
                status="done",
                report=json.dumps(report, ensure_ascii=False),
                finished_at=db.now(),
            )
            _set_progress(check_id, "done", 100)
        except Exception as e:  # noqa: BLE001
            db.update_check(check_id, status="error", error=str(e), finished_at=db.now())
            _set_progress(check_id, "error", 100)
    finally:
        _CAPACITY.release()


def _title_from(text: str, fallback: str) -> str:
    if fallback.strip():
        return fallback.strip()[:120]
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    return first_line[:60] or "未命名文档"


def _local_summary(aigc_part: list) -> dict | None:
    for e in aigc_part:
        if e.get("key") == "local":
            return e
    return None


def get_report(check_id: str) -> dict | None:
    row = db.get_check(check_id)
    if not row:
        return None
    data = dict(row)
    if data.get("report"):
        data["report"] = json.loads(data["report"])
    if data.get("options"):
        data["options"] = json.loads(data["options"])
    return data
