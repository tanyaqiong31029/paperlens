"""联网全网核查：把可疑句切成检索短语 → 多源检索 → 正文比对。

检索提供方（按句种语言自动编排，失败自动降级）：
- 学术库直查（最可靠，返回自带摘要无需抓页面）：
  OpenAlex（全球 OA 元数据）/ arXiv（exact phrase）/ Europe PMC（生物医学）
- 通用网页：Bing API / SerpAPI（配 Key 后优先）→ Bing 网页版 → DuckDuckGo 兜底
命中判定与本地查重同一套 shingle containment 算法，阈值相同。
"""

import contextlib
import html as html_lib
import json
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from .. import config, db
from . import segmenter

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
}
_TIMEOUT = 12
_MAX_PAGE = 300_000
_Q_DELAY = 1.2  # 检索间隔（礼貌抓取）
_ZH_MIN_NORM = 12  # 可疑句最小归一化长度（短句区分度不足，不查询）
_EN_MIN_WORDS = 8
_DEFAULT_BUDGET = 110  # 整体时间预算（秒），防止报告被联网核查拖死


# ---------------- HTTP 与页面正文抽取 ----------------


def _http_get(url: str, timeout: int = _TIMEOUT) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ct = (r.headers.get("Content-Type") or "").lower()
        if any(t in ct for t in ("pdf", "image", "json", "octet-stream")):
            return ""
        return r.read(_MAX_PAGE).decode("utf-8", "ignore")


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self._SKIP:
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def extract_text(page_html: str) -> str:
    p = _TextExtractor()
    with contextlib.suppress(Exception):
        p.feed(page_html)
    return re.sub(r"\s+", " ", " ".join(p.parts)).strip()


def fetch_page_text(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        return ""
    try:
        return extract_text(_http_get(url))
    except Exception:  # noqa: BLE001
        return ""


# ---------------- 检索提供方 ----------------
# 统一返回 [{"url","title","text"?}]；text 缺省时由调用方抓取页面。


def _strip_tags(s: str) -> str:
    return html_lib.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _search_bing_api(q: str) -> list[dict]:
    key = db.get_engine_keys().get("bing_api", {}).get("api_key") or ""
    req = urllib.request.Request(
        "https://api.bing.microsoft.com/v7.0/search?"
        + urllib.parse.urlencode({"q": f'"{q}"', "count": 10}),
        headers={**_UA, "Ocp-Apim-Subscription-Key": key},
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        data = json.loads(r.read().decode("utf-8", "ignore"))
    return [
        {"url": w.get("url", ""), "title": w.get("name", "")}
        for w in (data.get("webPages") or {}).get("value", [])
    ]


def _search_serpapi(q: str) -> list[dict]:
    key = db.get_engine_keys().get("serpapi", {}).get("api_key") or ""
    data = json.loads(
        _http_get(
            "https://serpapi.com/search.json?"
            + urllib.parse.urlencode(
                {
                    "q": f'"{q}"',
                    "num": 10,
                    "api_key": key,
                }
            )
        )
    )
    return [
        {"url": w.get("link", ""), "title": w.get("title", "")}
        for w in data.get("organic_results", [])
    ]


def _search_bing_html(q: str) -> list[dict]:
    txt = _http_get(
        "https://cn.bing.com/search?" + urllib.parse.urlencode({"q": f'"{q}"', "count": 10})
    )
    if len(txt) < 2000:
        raise RuntimeError("Bing 返回页面异常（可能被风控）")
    out = []
    for m in re.finditer(r'<h2[^>]*>\s*<a[^>]+href="(http[^"]+)"[^>]*>(.*?)</a>', txt, re.S):
        url, title = m.group(1), _strip_tags(m.group(2))
        if "bing.com" in urllib.parse.urlparse(url).netloc:
            continue
        out.append({"url": url, "title": title})
    return out


def _search_ddg(q: str) -> list[dict]:
    txt = _http_get("https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": f'"{q}"'}))
    out = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', txt, re.S):
        url = m.group(1)
        if "uddg=" in url:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            url = urllib.parse.unquote(qs.get("uddg", [url])[0])
        out.append({"url": url, "title": _strip_tags(m.group(2))})
    return out


def _search_openalex(q: str, kind: str) -> list[dict]:
    """OpenAlex 全库检索（title+abstract），结果自带摘要，直接可比对。"""
    from .crawler import MAILTO  # 复用 polite pool 邮箱

    filt = f"open_access.is_oa:true,language:{'zh' if kind == 'zh' else 'en'}"
    terms = " ".join(q.split()[:8]) if kind == "en" else q[:12]
    data = json.loads(
        _http_get(
            "https://api.openalex.org/works?"
            + urllib.parse.urlencode(
                {
                    "filter": f"{filt},title_and_abstract.search:{terms}",
                    "per-page": 5,
                    "mailto": MAILTO,
                }
            )
        )
    )
    out = []
    for w in data.get("results", []):
        inv = w.get("abstract_inverted_index")
        if not inv:
            continue
        pos_map = {}
        for word, positions in inv.items():
            for p in positions:
                pos_map[p] = word
        abstract = " ".join(pos_map[i] for i in sorted(pos_map))
        url = w.get("doi") or (w.get("primary_location") or {}).get("landing_page_url") or ""
        out.append(
            {
                "url": url,
                "title": w.get("display_name") or "",
                "text": f"{w.get('display_name') or ''}\n{abstract}",
            }
        )
    return out


def _search_arxiv(q: str) -> list[dict]:
    """arXiv exact phrase 检索（all:"..."），结果自带摘要。"""
    raw = _http_get(
        "http://export.arxiv.org/api/query?"
        + urllib.parse.urlencode(
            {
                "search_query": f'all:"{q}"',
                "max_results": 5,
            }
        )
    )
    import xml.etree.ElementTree as ET

    ns = "{http://www.w3.org/2005/Atom}"
    out = []
    try:
        root = ET.fromstring(raw.encode())
    except Exception:  # noqa: BLE001
        return out
    for e in root.findall(f"{ns}entry"):
        title = re.sub(r"\s+", " ", (e.findtext(f"{ns}title") or "")).strip()
        summary = re.sub(r"\s+", " ", (e.findtext(f"{ns}summary") or "")).strip()
        out.append(
            {
                "url": (e.findtext(f"{ns}id") or "").strip(),
                "title": title,
                "text": f"{title}\n{summary}",
            }
        )
    return out


def _search_europepmc(q: str) -> list[dict]:
    """Europe PMC 摘要精确短语检索。"""
    data = json.loads(
        _http_get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
            + urllib.parse.urlencode(
                {
                    "query": f'"{q}" AND OPEN_ACCESS:y',
                    "format": "json",
                    "pageSize": 5,
                    "resultType": "core",
                }
            )
        )
    )
    out = []
    for r in (data.get("resultList") or {}).get("result", []):
        abstract = re.sub(r"<[^>]+>", "", r.get("abstractText") or "")
        title = (r.get("title") or "").strip()
        doi = r.get("doi") or ""
        url = (
            f"https://doi.org/{doi}"
            if doi
            else (
                f"https://europepmc.org/article/{r.get('source')}/{r.get('id')}"
                if r.get("id")
                else ""
            )
        )
        out.append({"url": url, "title": title, "text": f"{title}\n{abstract}"})
    return out


_PROVIDER_FN = {
    "bing_api": _search_bing_api,
    "serpapi": _search_serpapi,
    "bing_html": _search_bing_html,
    "duckduckgo": _search_ddg,
    "openalex": _search_openalex,
    "arxiv": _search_arxiv,
    "europepmc": _search_europepmc,
}


def _provider_chain(kind: str) -> list[str]:
    keys = db.get_engine_keys()
    chain = []
    for k in ("bing_api", "serpapi"):
        if keys.get(k, {}).get("enabled") and keys[k].get("api_key"):
            chain.append(k)
    # 学术库直查优先（结构化、自带摘要、无反爬）
    chain.append("openalex")
    if kind == "en":
        chain += ["arxiv", "europepmc"]
    chain += ["bing_html", "duckduckgo"]
    return chain


# ---------------- 核心比对 ----------------


def _make_query(sent: dict) -> str:
    norm = sent.get("norm") or ""
    if sent.get("kind") == "zh":
        return norm[:16] if len(norm) >= 16 else norm
    return " ".join(norm.split()[:10])


def _match_in_page(sent: dict, query: str, page_text: str) -> dict | None:
    kind = sent["kind"]
    page_text = page_text[:150_000]
    page_norm = segmenter.normalize(page_text, kind)
    sent_norm = sent.get("norm") or ""

    threshold = config.ZH_SIM_THRESHOLD if kind == "zh" else config.EN_SIM_THRESHOLD

    # 快路径：归一化后原文子串命中
    if len(sent_norm) >= _ZH_MIN_NORM and sent_norm in page_norm:
        snippet = ""
        for ps in segmenter.split_sentences(page_text):
            if ps.kind == kind and query and query in segmenter.normalize(ps.text, kind):
                snippet = ps.text[:200]
                break
        return {"sim": 1.0, "snippet": snippet}

    # 句级 containment
    q_shingles = segmenter.shingles_norm(sent_norm, kind)
    if not q_shingles:
        return None
    best = None
    for ps in segmenter.split_sentences(page_text):
        if ps.kind != kind or ps.units < 6:
            continue
        sim = segmenter.similarity(q_shingles, segmenter.shingles(ps))
        if sim >= threshold and (best is None or sim > best["sim"]):
            best = {"sim": round(sim, 4), "snippet": ps.text[:200]}
    return best


def run(sent_results: list[dict], options: dict) -> dict:
    budget = int(options.get("web_check_budget", _DEFAULT_BUDGET))
    count = max(3, min(30, int(options.get("web_check_count", 10))))
    t0 = time.time()

    # 选择可疑句：本地未命中的句子（本地已命中的不再重复联网），长句优先
    def eligible(s: dict) -> bool:
        if s.get("matched"):
            return False
        norm = s.get("norm") or ""
        if s.get("kind") == "zh":
            return len(norm) >= _ZH_MIN_NORM
        return len(norm.split()) >= _EN_MIN_WORDS

    cands = sorted([s for s in sent_results if eligible(s)], key=lambda s: -s["units"])[:count]

    # 每种语言独立维护检索链与降级指针
    chains = {kind: _provider_chain(kind) for kind in ("zh", "en")}
    pi_by_kind = {"zh": 0, "en": 0}
    hits: list[dict] = []
    sources: dict[str, dict] = {}
    page_cache: dict[str, str] = {}
    queried = failed = 0
    last_error = ""
    dup_units = 0

    for s in cands:
        if time.time() - t0 > budget:
            break
        kind = s.get("kind") or "zh"
        chain = chains[kind]
        pi = pi_by_kind[kind]
        if pi >= len(chain):
            failed += 1
            continue
        q = _make_query(s)
        results, err = None, ""
        while pi < len(chain):
            try:
                fn = _PROVIDER_FN[chain[pi]]
                results = fn(q) if "openalex" not in chain[pi] else fn(q, kind)
                break
            except Exception as e:  # noqa: BLE001
                err = f"{chain[pi]}: {e}"
                pi += 1
        pi_by_kind[kind] = pi
        if results is None:
            if err:
                last_error = err
            failed += 1
            continue
        queried += 1
        via = chain[pi]

        for cand in results[:5]:
            url, title = cand.get("url", ""), cand.get("title", "")
            text = cand.get("text")
            if text is None:
                if url not in page_cache:
                    page_cache[url] = fetch_page_text(url)
                text = page_cache[url]
            if not text or not url:
                continue
            m = _match_in_page(s, q, text)
            if m:
                hits.append(
                    {
                        "start": s["start"],
                        "end": s["end"],
                        "text": s["text"],
                        "units": s["units"],
                        "url": url,
                        "title": title or url,
                        "sim": m["sim"],
                        "snippet": m["snippet"],
                        "via": via,
                    }
                )
                s["web"] = {"url": url, "title": title or url, "sim": m["sim"]}
                dup_units += s["units"]
                src = sources.setdefault(
                    url, {"url": url, "title": title or url, "units": 0, "hits": 0}
                )
                src["units"] += s["units"]
                src["hits"] += 1
                break
        time.sleep(_Q_DELAY)

    total_units = sum(s["units"] for s in sent_results) or 1
    src_list = sorted(sources.values(), key=lambda x: -x["units"])
    for e in src_list:
        e["rate"] = round(e["units"] / total_units * 100, 1)

    used = sorted({h.get("via", "") for h in hits} - {""}) or sorted(
        {chains[k][min(pi_by_kind[k], len(chains[k]) - 1)] for k in chains}
    )
    if queried == 0 and failed > 0:
        status = "error"
        note = f"检索失败（{last_error}）。可配置 Bing API/SerpAPI Key 提高稳定性。"
    elif queried < len(cands):
        status = "partial"
        note = f"时间预算内核查 {queried}/{len(cands)} 句"
    else:
        status = "ok"
        note = f"共核查 {queried} 句"
    return {
        "status": status,
        "provider": " → ".join(used) if used else "",
        "checked": queried,
        "candidates": len(cands),
        "failed": failed,
        "web_dup_rate": round(dup_units / total_units * 100, 1) if sent_results else 0.0,
        "web_dup_units": dup_units,
        "hits": hits,
        "sources": src_list,
        "note": note,
    }
