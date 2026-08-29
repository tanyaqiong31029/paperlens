"""PaperLens 论文检测中心 · FastAPI 后端入口。

安全模型（默认最小暴露）：
- 启动脚本默认绑定 127.0.0.1；绑定非回环地址须显式传参，且要求设置
  PAPERLENS_ADMIN_TOKEN（/api 下的写接口与报告读取随后要求 X-Admin-Token）；
- CORS 默认不启用（同源部署天然可用）；如需跨域，设 PAPERLENS_ALLOW_ORIGINS。
"""
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .services import parser
from .services import checker
from .services.aigc import engines as aigc_engines
from .services.corpus import CORPUS
from .services.exporter import export_html


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    _seed_corpus_if_empty()
    CORPUS.rebuild()
    # AIGC v2 的 n-gram LM 训练放后台线程，不阻塞启动（百万级 token 数秒完成）
    import threading
    from .services import ngram_lm
    threading.Thread(target=ngram_lm.rebuild_lm, daemon=True).start()
    yield


app = FastAPI(title=config.APP_NAME, version=config.APP_VERSION, lifespan=lifespan)

# CORS：默认关闭（同源部署不需要）。跨域需求时用环境变量显式开白名单。
_allow_origins = [o.strip() for o in os.environ.get("PAPERLENS_ALLOW_ORIGINS", "").split(",") if o.strip()]
if _allow_origins:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware, allow_origins=_allow_origins,
        allow_methods=["*"], allow_headers=["*"],
    )


@app.middleware("http")
async def admin_guard(request: Request, call_next):
    """设置 PAPERLENS_ADMIN_TOKEN 后，除健康/统计/引擎列表外全部要求令牌。

    令牌只接受请求头 X-Admin-Token（不提供 query-string 方式，避免令牌进入
    浏览器历史、代理日志与 Referer）。
    """
    if config.ADMIN_TOKEN:
        p = request.url.path
        if p.startswith("/api") and p not in ("/api/health", "/api/stats", "/api/engines"):
            if request.headers.get("x-admin-token") != config.ADMIN_TOKEN:
                return JSONResponse({"detail": "需要管理员令牌（X-Admin-Token）"}, status_code=401)
    return await call_next(request)


class BodySizeLimitMiddleware:
    """纯 ASGI 中间件：对 POST/PUT 的实际接收字节计数，超限即 413。

    覆盖 multipart / JSON / 表单等所有请求体（含分块传输、无 Content-Length
    的情况），限制发生在任何端点解析 body 之前。部署在 Nginx/Caddy 后时，
    建议同时在反代层配置 client_max_body_size / request_body max_size。
    """

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in ("POST", "PUT"):
            await self.app(scope, receive, send)
            return
        body = b""
        while True:
            msg = await receive()
            if msg["type"] == "http.request":
                body += msg.get("body", b"")
                if len(body) > self.max_bytes:
                    await send({
                        "type": "http.response.start", "status": 413,
                        "headers": [(b"content-type", b"application/json; charset=utf-8")],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": f'{{"detail":"请求体超过 {self.max_bytes // (1024 * 1024)}MB 上限"}}'.encode(),
                    })
                    return
                if not msg.get("more_body"):
                    break
            elif msg["type"] == "http.disconnect":
                return
        sent = {"done": False}

        async def buffered_receive():
            if not sent["done"]:
                sent["done"] = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, buffered_receive, send)


app.add_middleware(BodySizeLimitMiddleware, max_bytes=config.MAX_BODY_BYTES)


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
    # 请求体字节上限由 BodySizeLimitMiddleware 在网络层强制（413），
    # 这里只做业务级的正文长度上限。
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
    if len(content) > config.MAX_TEXT_CHARS:
        raise HTTPException(413, f"正文超过 {config.MAX_TEXT_CHARS} 字符上限")
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
    except RuntimeError as e:
        raise HTTPException(429, str(e))
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
