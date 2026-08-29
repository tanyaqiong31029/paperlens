"""OA 论文采集器：arXiv / OpenAlex / DOAJ / Europe PMC 四个开放学术数据源。

均为官方公开 API，礼貌抓取（分页间隔 + 连续失败熔断 + 停止标志），
文档按 title 去重后入库并实时加入查重倒排索引。OpenAlex 索引全球
2.5 亿+ 篇文献元数据，可用 language:zh 过滤中文 OA 论文。
"""
import json
import re
import threading
import time
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET

from .. import db
from .corpus import CORPUS

MAILTO = "paperlens-demo@example.org"
_UA = {"User-Agent": f"PaperLens/1.0 (academic similarity demo; mailto:{MAILTO})"}


def _get(url: str, params: dict | None = None, timeout: int = 25) -> bytes:
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------- 各数据源适配器（generator：逐篇产出） ----------------

def iter_arxiv(query: str, target: int, stop, errors: list):
    """arXiv 预印本（英文为主），Atom API。"""
    ns = "{http://www.w3.org/2005/Atom}"
    start, fails = 0, 0
    while start < target and not stop():
        try:
            raw = _get("http://export.arxiv.org/api/query", {
                "search_query": query.strip() or "cat:cs.CL",
                "start": start,
                "max_results": min(100, target - start),
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            })
            root = ET.fromstring(raw)
            entries = root.findall(f"{ns}entry")
            if not entries:
                return
            for e in entries:
                title = re.sub(r"\s+", " ", (e.findtext(f"{ns}title") or "")).strip()
                summary = re.sub(r"\s+", " ", (e.findtext(f"{ns}summary") or "")).strip()
                link = (e.findtext(f"{ns}id") or "").strip()
                if title and len(summary) >= 80:
                    yield {"title": title, "content": f"{title}\n\n{summary}",
                           "url": link, "origin": "oa:arxiv"}
            start += 100
            fails = 0
            time.sleep(3)  # arXiv 官方要求请求间隔
        except Exception as e:  # noqa: BLE001
            errors.append(f"arXiv: {e}")
            fails += 1
            if fails >= 3:
                return
            time.sleep(6)


def iter_openalex(lang: str, query: str, target: int, stop, errors: list):
    """OpenAlex：全球最大开放学术元数据库，OA 子集 + 语言过滤。"""
    cursor, fails = "*", 0
    while not stop():
        try:
            filt = f"open_access.is_oa:true,language:{lang}"
            q = query.strip().replace(",", " ")
            if q:
                filt += f",title_and_abstract.search:{q}"
            data = json.loads(_get("https://api.openalex.org/works", {
                "filter": filt,
                "per-page": 200,
                "cursor": cursor,
                "sort": "publication_date:desc",
                "mailto": MAILTO,
            }))
            for w in data.get("results", []):
                inv = w.get("abstract_inverted_index")
                if not inv:
                    continue
                pos_map = {}
                for word, positions in inv.items():
                    for p in positions:
                        pos_map[p] = word
                abstract = " ".join(pos_map[i] for i in sorted(pos_map))
                title = (w.get("display_name") or "").strip()
                if not title or len(abstract) < 80:
                    continue
                url = w.get("doi") or (w.get("primary_location") or {}).get("landing_page_url") or ""
                yield {"title": title, "content": f"{title}\n\n{abstract}",
                       "url": url, "origin": f"oa:openalex-{lang}"}
            cursor = (data.get("meta") or {}).get("next_cursor")
            if not cursor:
                return
            fails = 0
            time.sleep(0.6)
        except Exception as e:  # noqa: BLE001
            errors.append(f"OpenAlex: {e}")
            fails += 1
            if fails >= 3:
                return
            time.sleep(5)


def iter_doaj(query: str, target: int, stop, errors: list):
    """DOAJ 开放获取期刊文章目录（含部分中文期刊）。"""
    page, fails = 1, 0
    while not stop():
        try:
            q = urllib.parse.quote(query.strip() or "*")
            data = json.loads(_get(
                f"https://doaj.org/api/v2/search/articles/{q}",
                {"pageSize": 100, "page": page},
            ))
            results = data.get("results", [])
            for r in results:
                bj = r.get("bibjson") or {}
                title = (bj.get("title") or "").strip()
                abstract = (bj.get("abstract") or "").strip()
                link = ""
                for l in bj.get("link", []):
                    if l.get("type") == "fulltext" and l.get("url"):
                        link = l["url"]
                        break
                if title and len(abstract) >= 80:
                    yield {"title": title, "content": f"{title}\n\n{abstract}",
                           "url": link, "origin": "oa:doaj"}
            if len(results) < 100:
                return
            page += 1
            fails = 0
            time.sleep(1)
        except Exception as e:  # noqa: BLE001
            errors.append(f"DOAJ: {e}")
            fails += 1
            if fails >= 3:
                return
            time.sleep(5)


def iter_europepmc(query: str, target: int, stop, errors: list):
    """Europe PMC：生物医学/生命科学 OA 文献，含摘要。"""
    page, fails = 1, 0
    while not stop():
        try:
            q = f"({query.strip()}) AND OPEN_ACCESS:y" if query.strip() else "OPEN_ACCESS:y"
            data = json.loads(_get("https://www.ebi.ac.uk/europepmc/webservices/rest/search", {
                "query": q, "format": "json", "pageSize": 100,
                "page": page, "resultType": "core",
            }))
            results = (data.get("resultList") or {}).get("result", [])
            for r in results:
                title = (r.get("title") or "").strip()
                abstract = re.sub(r"<[^>]+>", "", r.get("abstractText") or "").strip()
                doi = r.get("doi") or ""
                if doi:
                    url = f"https://doi.org/{doi}"
                elif r.get("id") and r.get("source"):
                    url = f"https://europepmc.org/article/{r['source']}/{r['id']}"
                else:
                    url = ""
                if title and len(abstract) >= 80:
                    yield {"title": title, "content": f"{title}\n\n{abstract}",
                           "url": url, "origin": "oa:europepmc"}
            if len(results) < 100:
                return
            page += 1
            fails = 0
            time.sleep(1)
        except Exception as e:  # noqa: BLE001
            errors.append(f"EuropePMC: {e}")
            fails += 1
            if fails >= 3:
                return
            time.sleep(5)


SOURCES: dict[str, dict] = {
    "arxiv": {
        "name": "arXiv",
        "region": "国际",
        "langs": "英文",
        "desc": "计算机/物理/数学等预印本 240 万+，官方 API，含标题与摘要",
        "default_query": "cat:cs.CL OR cat:cs.AI",
        "max_target": 5000,
    },
    "openalex-en": {
        "name": "OpenAlex（国际 OA · 英文）",
        "region": "国际",
        "langs": "英文",
        "desc": "索引全球 2.5 亿+ 篇文献元数据，采集其 OA 子集（按时间倒序增量拉取）",
        "default_query": "",
        "max_target": 20000,
    },
    "openalex-zh": {
        "name": "OpenAlex（国际 OA · 中文）",
        "region": "国内",
        "langs": "中文",
        "desc": "OpenAlex 收录的中文 OA 论文（language:zh 过滤），覆盖国内 OA 期刊",
        "default_query": "",
        "max_target": 20000,
    },
    "doaj": {
        "name": "DOAJ",
        "region": "国际+国内",
        "langs": "多语种",
        "desc": "开放获取期刊目录，2 万+ 期刊、千万级文章记录，含中文 OA 期刊",
        "default_query": "*",
        "max_target": 10000,
    },
    "europepmc": {
        "name": "Europe PMC",
        "region": "国际",
        "langs": "英文",
        "desc": "生物医学与生命科学 OA 文献（含 PubMed Central），适合医学论文比对",
        "default_query": "",
        "max_target": 10000,
    },
}

_ADAPTERS = {
    "arxiv": lambda q, t, stop, errs: iter_arxiv(q, t, stop, errs),
    "openalex-en": lambda q, t, stop, errs: iter_openalex("en", q, t, stop, errs),
    "openalex-zh": lambda q, t, stop, errs: iter_openalex("zh", q, t, stop, errs),
    "doaj": lambda q, t, stop, errs: iter_doaj(q, t, stop, errs),
    "europepmc": lambda q, t, stop, errs: iter_europepmc(q, t, stop, errs),
}


def sources_info() -> list[dict]:
    return [{**{k: v for k, v in m.items()}, "key": k} for k, m in SOURCES.items()]


# ---------------- 任务管理 ----------------

MAX_CONCURRENT_CRAWLS = 2          # 并发采集任务上限（有界，避免线程无限制增长）
_active_jobs = 0
_jobs_lock = threading.Lock()


def start_job(source: str, query: str, target: int) -> str:
    global _active_jobs
    if source not in SOURCES:
        raise ValueError(f"未知数据源：{source}")
    with _jobs_lock:
        if _active_jobs >= MAX_CONCURRENT_CRAWLS:
            raise RuntimeError(f"已有 {MAX_CONCURRENT_CRAWLS} 个采集任务在运行，请等待完成或先停止")
        _active_jobs += 1
    target = max(20, min(int(target), SOURCES[source]["max_target"]))
    job_id = uuid.uuid4().hex[:10]
    db.create_job(job_id, source, query.strip(), target)
    threading.Thread(target=_run_job, args=(job_id,), daemon=True).start()
    return job_id


def _release_job() -> None:
    global _active_jobs
    with _jobs_lock:
        _active_jobs = max(0, _active_jobs - 1)


def _run_job(job_id: str) -> None:
    job = db.get_job(job_id)
    if not job:
        return
    source, query, target = job["source"], job["query"] or "", int(job["target"])
    errors: list[str] = []

    def should_stop() -> bool:
        j = db.get_job(job_id)
        return (not j) or j["status"] in ("stop_requested", "error")

    def adapter(q, t, stop, errs):
        return _ADAPTERS[source](q, t, stop, errs)

    fetched = added = 0
    try:
        for doc in adapter(query, target, should_stop, errors):
            fetched += 1
            try:
                if not db.doc_title_exists(doc["title"]):
                    did = db.add_doc(
                        doc["title"][:200], doc["content"],
                        len(doc["content"].replace(" ", "").replace("\n", "")),
                        is_builtin=False, origin=doc["origin"], source_url=doc["url"] or "",
                    )
                    CORPUS.add_and_index(did)
                    added += 1
            except Exception as e:  # noqa: BLE001
                errors.append(f"入库: {e}")
            if fetched % 25 == 0:
                db.update_job(job_id, fetched=fetched, added=added,
                              message="；".join(errors[-2:]) or None)
            if fetched >= target or fetched - added > 800:  # 达到目标或大量重复标题时收束
                break
        status = "stopped" if should_stop() else "done"
        msg = f"采集 {fetched} 篇，新增 {added} 篇"
        if errors:
            msg += "；" + "；".join(errors[-2:])
        db.update_job(job_id, status=status, fetched=fetched, added=added, message=msg[:400])
    except Exception as e:  # noqa: BLE001
        db.update_job(job_id, status="error", fetched=fetched, added=added,
                      message=f"{e}；errors: {'；'.join(errors[-2:])}"[:400])
    finally:
        _release_job()
