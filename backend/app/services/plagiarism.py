"""查重主流程：分句 → 倒排召回 → 精确比对 → 片段合并 → 重复率。

口径与主流查重报告一致：
- 总重复率 = 相似句累计字数（去重后，规范引用部分剔除）/ 全文字数；
- 规范引用口径：句内被引号包裹且占比 ≥60% 的命中句计入 quote_rate（引用率），
  不计入 total_rate，与知网"引用率/复制比"分离的呈现方式对应；
- 同一句命中多个来源时取最相似来源展示，其余来源保留在 all_sources；
- 相邻相似句合并为"片段"，与知网/PaperPass 报告的标红块对应。
"""

import re

from .. import config
from . import segmenter
from .corpus import CORPUS
from .parser import strip_references

_QUOTE_RE = re.compile(r"“([^”]*)”|\"([^\"]*)\"|‘([^’]*)’")


def quoted_units(text: str, kind: str) -> int:
    """句内被引号包裹片段的单位数（中文按字、英文按词）——规范引用口径。"""
    total = 0
    for m in _QUOTE_RE.finditer(text):
        inner = next((g for g in m.groups() if g is not None), "")
        total += len(inner) if kind == "zh" else len(inner.split())
    return total


def _threshold_for(kind: str) -> float:
    return config.ZH_SIM_THRESHOLD if kind == "zh" else config.EN_SIM_THRESHOLD


def run(text: str, options: dict) -> dict:
    strip_refs = options.get("strip_references", True)
    body = strip_references(text) if strip_refs else text
    sents = segmenter.split_sentences(body)

    # 文末残余若被 strip 截断，最后一行仍会进入 body，无碍比对。
    total_units = sum(s.units for s in sents)
    dup_units = 0  # 计入复制比的单位（规范引用剔除后）
    quote_units_total = 0  # 规范引用单位（引号内），单独口径

    sent_results: list[dict] = []
    sources: dict[int, dict] = {}
    src_order: list[int] = []
    all_src_counts: dict[int, int] = {}  # 每个来源文档在逐句 all_sources 中的出现次数

    for s in sents:
        th = _threshold_for(s.kind)
        cands = CORPUS.find_similar(s, th)
        if cands:
            best = cands[0]
            if best.doc_id not in sources:
                sources[best.doc_id] = {
                    "doc_id": best.doc_id,
                    "title": best.doc_title,
                    "dup_units": 0,
                    "hits": 0,
                }
                src_order.append(best.doc_id)
            sources[best.doc_id]["dup_units"] += s.units
            sources[best.doc_id]["hits"] += 1
            # 规范引用口径：引号内占比 ≥60% 的命中句计入引用率而非复制比
            q = quoted_units(s.text, s.kind)
            if q >= 0.6 * max(1, s.units):
                quote_units_total += s.units
            else:
                dup_units += s.units
                quote_units_total += min(q, s.units)
            sent_results.append(
                {
                    "start": s.start,
                    "end": s.end,
                    "text": s.text,
                    "units": s.units,
                    "norm": s.norm,
                    "kind": s.kind,
                    "matched": True,
                    "quote_units": q,
                    "best": {
                        "doc_id": best.doc_id,
                        "title": best.doc_title,
                        "src_text": best.sent_text,
                        "sim": best.sim,
                    },
                    "all_sources": [
                        {
                            "doc_id": c.doc_id,
                            "title": c.doc_title,
                            "src_text": c.sent_text,
                            "sim": c.sim,
                        }
                        for c in cands
                    ],
                }
            )
            for c in cands:
                all_src_counts[c.doc_id] = all_src_counts.get(c.doc_id, 0) + 1
        else:
            quote_units_total += quoted_units(s.text, s.kind)
            sent_results.append(
                {
                    "start": s.start,
                    "end": s.end,
                    "text": s.text,
                    "units": s.units,
                    "norm": s.norm,
                    "kind": s.kind,
                    "matched": False,
                    "quote_units": quoted_units(s.text, s.kind),
                }
            )

    rate = round(dup_units / total_units * 100, 1) if total_units else 0.0
    quote_rate = round(quote_units_total / total_units * 100, 1) if total_units else 0.0

    # 片段合并：相邻相似句（允许隔 1 个未命中短句）
    fragments: list[dict] = []
    i = 0
    while i < len(sent_results):
        if sent_results[i]["matched"]:
            j = i
            gap = 0
            last = i
            while j + 1 < len(sent_results):
                nxt = sent_results[j + 1]
                if nxt["matched"]:
                    gap = 0
                    last = j + 1
                else:
                    gap += 1
                    if gap > config.FRAG_MERGE_GAP:
                        break
                j += 1
            group = sent_results[i : last + 1]
            matched_in = [g for g in group if g["matched"]]
            frag_units = sum(g["units"] for g in matched_in)
            by_src: dict[int, float] = {}
            for g in matched_in:
                by_src[g["best"]["doc_id"]] = by_src.get(g["best"]["doc_id"], 0) + g["units"]
            top_src = max(by_src.items(), key=lambda kv: kv[1])
            top = next(g["best"] for g in matched_in if g["best"]["doc_id"] == top_src[0])
            fragments.append(
                {
                    "start": group[0]["start"],
                    "end": group[-1]["end"],
                    "text": "".join(g["text"] for g in group),
                    "dup_units": frag_units,
                    "rate": round(frag_units / total_units * 100, 1) if total_units else 0,
                    "best_source": top,
                    "all_sources": _merge_frag_sources(matched_in),
                }
            )
            i = last + 1
        else:
            i += 1

    src_list = []
    for did in src_order:
        sinfo = sources[did]
        src_list.append(
            {
                **sinfo,
                "rate": round(sinfo["dup_units"] / total_units * 100, 1) if total_units else 0,
            }
        )
    src_list.sort(key=lambda x: -x["dup_units"])
    src_list = _cluster_near_duplicate_sources(src_list, all_src_counts, total_units)

    return {
        "total_rate": rate,
        "quote_rate": quote_rate,
        "dup_units": dup_units,
        "total_units": total_units,
        "sentence_count": len(sents),
        "matched_sentences": sum(1 for r in sent_results if r["matched"]),
        "fragments": fragments,
        "sources": src_list,
        "sent_results": sent_results,
    }


def _cluster_near_duplicate_sources(
    src_list: list[dict], all_src_counts: dict[int, int], total_units: int
) -> list[dict]:
    """SimHash 近重复来源聚类：同一文献的不同版本合并展示。

    句级 best 只会选中一个来源，其近重复版本（SimHash 汉明距 ≤12）出现在
    all_sources 计数中——把它们并入主来源的 variants，报告展示为
    "该来源另有 N 个近似版本"。"""
    from .fingerprint import is_near_duplicate

    merged: list[dict] = []
    claimed: set[int] = set()
    for s in src_list:
        fp = CORPUS.fingerprints.get(s["doc_id"])
        variants: list[dict] = []
        if fp is not None:
            for d, hits in all_src_counts.items():
                if d in claimed or d == s["doc_id"]:
                    continue
                dfp = CORPUS.fingerprints.get(d)
                if dfp is None:
                    continue
                doc = CORPUS.docs.get(d)
                if doc is None:
                    continue
                if is_near_duplicate(fp, dfp, max_h=12):
                    variants.append({"doc_id": d, "title": doc.title, "hits": hits})
                    claimed.add(d)
        merged.append({**s, "variants": variants})
    merged.sort(key=lambda x: -x["dup_units"])
    return merged


def _merge_frag_sources(matched: list[dict]) -> list[dict]:
    agg: dict[int, dict] = {}
    for g in matched:
        for src in g["all_sources"]:
            e = agg.setdefault(
                src["doc_id"],
                {
                    "doc_id": src["doc_id"],
                    "title": src["title"],
                    "hits": 0,
                    "sim": 0.0,
                    "src_text": src["src_text"],
                },
            )
            e["hits"] += 1
            e["sim"] = max(e["sim"], src["sim"])
    out = sorted(agg.values(), key=lambda x: -x["hits"])
    for e in out:
        e.pop("hits", None)
    return out
