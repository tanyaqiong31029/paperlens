"""PaperLens 论文检测中心 · FastAPI 后端入口。

生产模式下托管 frontend/dist（React 构建产物），单端口部署；
开发模式可 `uvicorn app.main:app --reload` 配合 Vite dev server（5173）。
"""
import json
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .services import parser
from .services import checker
from .services.aigc import engines as aigc_engines
from .services.corpus import CORPUS
from .services.exporter import export_html

app = FastAPI(title=config.APP_NAME, version=config.APP_VERSION)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    db.init_db()
    _seed_corpus_if_empty()
    CORPUS.rebuild()
    # AIGC v2 的 n-gram LM 训练放后台线程，不阻塞启动（百万级 token 数秒完成）
    import threading
    from .services import ngram_lm
    threading.Thread(target=ngram_lm.rebuild_lm, daemon=True).start()


def _seed_corpus_if_empty() -> None:
    if db.all_docs_full():
        return
    seed_dir = config.BASE_DIR / "seed_corpus"
    for f in sorted(seed_dir.glob("*.json")):
        docs = json.loads(f.read_text(encoding="utf-8"))
        for d in docs:
            db.add_doc(d["title"], d["content"], len(d["content"]), is_builtin=True)


# ---------------- health & stats ----------------
@app.get("/api/health")
def health():
    return {"status": "ok", "app": config.APP_NAME, "version": config.APP_VERSION}


@app.get("/api/stats")
def stats():
    s = CORPUS.stats()
    checks = db.list_checks()
    return {
        "corpus": s,
        "total_checks": len(checks),
        "engines": len(aigc_engines.list_engines()),
    }


# ---------------- 检测 ----------------
@app.post("/api/checks")
async def create_check(
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
    title: str = Form(""),
    mode: str = Form("full"),            # full / plagiarism / aigc
    strip_references: bool = Form(True),
    web_check: bool = Form(False),       # 联网全网核查
    web_check_count: int = Form(10),
):
    content = ""
    name = ""
    if file is not None and file.filename:
        data = await file.read()
        name = file.filename
        try:
            content = parser.parse_upload(name, data)
        except parser.ParseError as e:
            raise HTTPException(400, str(e))
    elif text:
        content = text
    if len(content.strip()) < 50:
        raise HTTPException(400, "正文过短（至少 50 字符），请检查文件内容或直接粘贴文本")

    display_title = title.strip() or (Path(name).stem if name else (content.strip().splitlines()[0][:40] if content.strip() else "未命名"))
    options = {
        "mode": mode,
        "strip_references": strip_references,
        "web_check": web_check,
        "web_check_count": max(3, min(30, web_check_count)),
        "title": display_title,
    }
    check_id = checker.submit(display_title, content, options)
    return {"check_id": check_id}


@app.get("/api/checks")
def list_checks():
    return [dict(r) for r in db.list_checks()]


@app.get("/api/checks/{check_id}")
def get_check(check_id: str):
    data = checker.get_report(check_id)
    if not data:
        raise HTTPException(404, "报告不存在")
    return data


@app.delete("/api/checks/{check_id}")
def remove_check(check_id: str):
    db.delete_check(check_id)
    return {"ok": True}


@app.get("/api/checks/{check_id}/export")
def export_report(check_id: str):
    html_text = export_html(check_id)
    if not html_text:
        raise HTTPException(404, "报告不存在或尚未完成")
    row = db.get_check(check_id)
    safe_title = "".join(c for c in (row["title"] or check_id) if c.isalnum() or c in "-_ ")[:40] or check_id
    return HTMLResponse(html_text, headers={
        "Content-Disposition": f"attachment; filename=report_{check_id}.html"
    })


# ---------------- 自建文档库 ----------------
@app.post("/api/library/documents")
async def add_library_doc(
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
    title: str = Form(""),
):
    content = ""
    name = ""
    if file is not None and file.filename:
        data = await file.read()
        name = file.filename
        try:
            content = parser.parse_upload(name, data)
        except parser.ParseError as e:
            raise HTTPException(400, str(e))
    elif text:
        content = text
    if len(content.strip()) < 20:
        raise HTTPException(400, "文档内容过短")
    doc_title = title.strip() or Path(name).stem if name else (title.strip() or content.strip().splitlines()[0][:40])
    doc_id = db.add_doc(doc_title, content, len(content.replace(" ", "").replace("\n", "")))
    CORPUS.add_and_index(doc_id)
    return {"id": doc_id, "title": doc_title}


@app.get("/api/library/documents")
def list_library():
    return [dict(r) for r in db.list_docs()]


@app.delete("/api/library/documents/{doc_id}")
def delete_library_doc(doc_id: int):
    if not db.delete_doc(doc_id):
        raise HTTPException(400, "内置语料不可删除或文档不存在")
    CORPUS.remove_doc(doc_id)
    return {"ok": True}


# ---------------- AIGC 引擎 ----------------
@app.get("/api/engines")
def list_all_engines():
    return aigc_engines.list_engines()


@app.post("/api/engines/{key}/config")
def config_engine(key: str, api_key: str = Form(""), enabled: bool = Form(True)):
    if key not in config.EXTERNAL_ENGINES and key not in config.SEARCH_PROVIDERS:
        raise HTTPException(404, "该引擎不支持 API 配置")
    db.set_engine_key(key, api_key, enabled)
    return {"ok": True}


# ---------------- 语料采集（OA 爬虫） ----------------
from .services import crawler  # noqa: E402


@app.get("/api/crawl/sources")
def crawl_sources():
    return crawler.sources_info()


@app.post("/api/crawl/jobs")
async def start_crawl(request: Request):
    body = await request.json()
    try:
        job_id = crawler.start_job(
            source=str(body.get("source", "")),
            query=str(body.get("query", "") or ""),
            target=int(body.get("target", 200)),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"job_id": job_id}


@app.get("/api/crawl/jobs")
def list_crawl_jobs():
    return [dict(r) for r in db.list_jobs()]


@app.post("/api/crawl/jobs/{job_id}/stop")
def stop_crawl(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if job["status"] == "running":
        db.update_job(job_id, status="stop_requested")
    return {"ok": True}


# ---------------- 降重 · 降AIGC ----------------
from .services import rewriter  # noqa: E402


@app.post("/api/reduce")
async def reduce_text(request: Request):
    body = await request.json()
    text = str(body.get("text", ""))
    mode = str(body.get("mode", "both"))
    if mode not in ("dedup", "humanize", "both"):
        raise HTTPException(400, "mode 必须是 dedup / humanize / both")
    if len(text.strip()) < 50:
        raise HTTPException(400, "正文过短（至少 50 字符）")
    return rewriter.rewrite(text, mode)


# ---------------- 静态托管（生产模式）----------------
DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        candidate = DIST / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
