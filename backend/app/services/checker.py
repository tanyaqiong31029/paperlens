"""检测任务编排：查重 + AIGC 多引擎，后台线程执行，DB 存状态与报告。"""
import json
import threading
import uuid

from .. import db
from . import plagiarism, segmenter
from .aigc import engines as aigc_engines
from .corpus import CORPUS


def submit(title: str, text: str, options: dict) -> str:
    check_id = uuid.uuid4().hex[:12]
    db.create_check(check_id, title, options)
    t = threading.Thread(target=_run, args=(check_id, text, options), daemon=True)
    t.start()
    return check_id


def _run(check_id: str, text: str, options: dict) -> None:
    try:
        db.update_check(check_id, status="running")
        lang = segmenter.detect_language(text)
        db.update_check(check_id, language=lang, word_count=len(text.replace(" ", "").replace("\n", "")))

        do_plag = options.get("mode", "full") in ("full", "plagiarism")
        do_aigc = options.get("mode", "full") in ("full", "aigc")

        plag_part = plagiarism.run(text, options) if do_plag else None

        # 联网全网核查：对本地未命中的可疑句做搜索引擎比对
        if plag_part is not None and options.get("web_check"):
            from . import webcheck
            try:
                plag_part["web"] = webcheck.run(plag_part["sent_results"], options)
            except Exception as e:  # noqa: BLE001
                plag_part["web"] = {"status": "error", "note": f"联网核查异常：{e}"}

        aigc_part = aigc_engines.detect_all(text, lang) if do_aigc else None

        if plag_part is not None:
            db.update_check(check_id, title=_title_from(text, options.get("title", "")))

        report = {
            "plagiarism": plag_part,
            "aigc": {
                "engines": aigc_part,
                "local": _local_summary(aigc_part) if aigc_part else None,
            } if aigc_part else None,
            "options": options,
        }
        db.update_check(check_id, status="done", report=json.dumps(report, ensure_ascii=False),
                        finished_at=db.now())
    except Exception as e:  # noqa: BLE001
        db.update_check(check_id, status="error", error=str(e), finished_at=db.now())


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
