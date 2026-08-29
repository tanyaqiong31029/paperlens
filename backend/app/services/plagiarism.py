"""查重主流程：分句 → 倒排召回 → 精确比对 → 片段合并 → 重复率。

口径与主流查重报告一致：
- 总重复率 = 相似句累计字数（去重后）/ 全文字数；
- 同一句命中多个来源时取最相似来源展示，其余来源保留在 all_sources；
- 相邻相似句合并为"片段"，与知网/PaperPass 报告的标红块对应。
"""
from . import segmenter
from .parser import strip_references
from .corpus import CORPUS
from .. import config


def _threshold_for(kind: str) -> float:
    return config.ZH_SIM_THRESHOLD if kind == "zh" else config.EN_SIM_THRESHOLD


def run(text: str, options: dict) -> dict:
    strip_refs = options.get("strip_references", True)
    body = strip_references(text) if strip_refs else text
    lang = segmenter.detect_language(text)
    sents = segmenter.split_sentences(body)

    # 文末残余若被 strip 截断，最后一行仍会进入 body，无碍比对。
    total_units = sum(s.units for s in sents)
    dup_units = 0

    sent_results: list[dict] = []
    sources: dict[int, dict] = {}
    src_order: list[int] = []

    for s in sents:
        th = _threshold_for(s.kind)
        cands = CORPUS.find_similar(s, th)
        if cands:
            dup_units += s.units
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
            sent_results.append({
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "units": s.units,
                "norm": s.norm,
                "kind": s.kind,
                "matched": True,
                "best": {
                    "doc_id": best.doc_id,
                    "title": best.doc_title,
                    "src_text": best.sent_text,
                    "sim": best.sim,
                },
                "all_sources": [
                    {"doc_id": c.doc_id, "title": c.doc_title, "src_text": c.sent_text, "sim": c.sim}
                    for c in cands
                ],
            })
        else:
            sent_results.append({
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "units": s.units,
                "norm": s.norm,
                "kind": s.kind,
                "matched": False,
            })

    rate = round(dup_units / total_units * 100, 1) if total_units else 0.0

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
            group = sent_results[i: last + 1]
            matched_in = [g for g in group if g["matched"]]
            frag_units = sum(g["units"] for g in matched_in)
            by_src: dict[int, float] = {}
            for g in matched_in:
                by_src[g["best"]["doc_id"]] = by_src.get(g["best"]["doc_id"], 0) + g["units"]
            top_src = max(by_src.items(), key=lambda kv: kv[1])
            top = next(g["best"] for g in matched_in if g["best"]["doc_id"] == top_src[0])
            fragments.append({
                "start": group[0]["start"],
                "end": group[-1]["end"],
                "text": "".join(g["text"] for g in group),
                "dup_units": frag_units,
                "rate": round(frag_units / total_units * 100, 1) if total_units else 0,
                "best_source": top,
                "all_sources": _merge_frag_sources(matched_in),
            })
            i = last + 1
        else:
            i += 1

    src_list = []
    for did in src_order:
        sinfo = sources[did]
        src_list.append({
            **sinfo,
            "rate": round(sinfo["dup_units"] / total_units * 100, 1) if total_units else 0,
        })
    src_list.sort(key=lambda x: -x["dup_units"])

    return {
        "total_rate": rate,
        "dup_units": dup_units,
        "total_units": total_units,
        "sentence_count": len(sents),
        "matched_sentences": sum(1 for r in sent_results if r["matched"]),
        "fragments": fragments,
        "sources": src_list,
        "sent_results": sent_results,
    }


def _merge_frag_sources(matched: list[dict]) -> list[dict]:
    agg: dict[int, dict] = {}
    for g in matched:
        for src in g["all_sources"]:
            e = agg.setdefault(src["doc_id"], {"doc_id": src["doc_id"], "title": src["title"], "hits": 0, "sim": 0.0, "src_text": src["src_text"]})
            e["hits"] += 1
            e["sim"] = max(e["sim"], src["sim"])
    out = sorted(agg.values(), key=lambda x: -x["hits"])
    for e in out:
        e.pop("hits", None)
    return out
