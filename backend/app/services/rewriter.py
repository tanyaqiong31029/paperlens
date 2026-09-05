"""降重 · 降AIGC 改写引擎（规则版，离线）。

两个目标、三组手段：
- 降重（dedup）：对被查重命中的句子做同义替换 + 长句切分，破坏指纹连续性；
- 降AIGC（humanize）：对高 AI 疑似句做套话改写（AI 高频短语 → 平实表达）、
  连接词稀释、长句切分，直接压低 v2 引擎的六个统计特征与 LM 平滑度。

设计原则：
- 只做**表达层**改写，不改语义立场；每个改动都给出 reason 供人工复核；
- 规则引擎改写上限明显低于 LLM，接口留了 LLM 适配位（见 README 路线图）；
- 改写完成后自动用同一套查重/AIGC 引擎复测，输出前后对比。
  产品定位：辅助修改自己撰写/引用改写的段落，不得用于掩盖抄袭（见免责声明）。
"""

import re

from . import segmenter
from .aigc import local_engine
from .corpus import CORPUS
from .plagiarism import run as plag_run

# ---------------- 改写资源（自建，可继续扩充） ----------------

CLICHE_ZH: dict[str, str] = {
    "综上所述": "从以上分析来看",
    "总而言之": "概括起来讲",
    "值得注意的是": "需要留意的一点是",
    "需要指出的是": "这里要说明的是",
    "具有重要意义": "有实际价值",
    "奠定坚实基础": "打下了基础",
    "提供有力支持": "提供了支持",
    "日益增长": "越来越多",
    "不断涌现": "陆续出现",
    "密切相关": "关系紧密",
    "取得显著成效": "效果明显",
    "日趋完善": "越来越完善",
    "深度融合": "深度结合",
    "深入探讨": "详细讨论",
    "深入研究": "细致研究",
    "进行了深入研究": "做了细致研究",
    "进行了系统研究": "做了系统梳理",
    "提供新的思路": "给出了一条可行思路",
    "机遇和挑战": "机会与难题",
    "发挥重要作用": "起到关键作用",
    "全方位": "多方面",
    "多层次": "分层次",
    "赋能": "带动",
    "助力": "推动",
}

CLICHE_EN: dict[str, str] = {
    "it is important to note that": "notably,",
    "it is worth noting that": "notably,",
    "plays a crucial role in": "is key to",
    "plays a vital role in": "is key to",
    "in conclusion": "to sum up",
    "delve into": "look into",
    "leverage": "use",
    "utilize": "use",
    "comprehensive": "thorough",
    "pivotal": "key",
    "robust": "strong",
    "foster": "encourage",
    "underscore": "highlight",
    "pave the way for": "open the door to",
    "in the realm of": "in",
    "ever-evolving": "fast-changing",
    "multifaceted": "varied",
    "holistic": "overall",
    "seamless": "smooth",
    "cutting-edge": "recent",
    "landscape of": "field of",
    "moreover": "also",
    "furthermore": "besides",
}

SYN_ZH: dict[str, str] = {
    "研究表明": "已有研究显示",
    "结果显示": "数据上看",
    "随着": "伴随",
    "提升": "提高",
    "促进": "推动",
    "导致": "引发",
    "因此": "为此",
    "此外": "另外",
    "应用": "运用",
    "采用": "使用",
    "显著": "明显",
    "影响": "作用",
    "探讨": "讨论",
    "目前": "当前",
    "大量": "许多",
    "主要": "核心",
    "以及": "和",
    "通过": "借助",
    "基于": "依据",
    "进一步": "更深入地",
}

SYN_EN: dict[str, str] = {
    "significant": "notable",
    "demonstrate": "show",
    "investigate": "examine",
    "examine": "look at",
    "individuals": "people",
    "approximately": "about",
    "numerous": "many",
    "additionally": "also",
    "subsequently": "later",
    "primarily": "mainly",
    "frequently": "often",
    "currently": "at present",
    "obtain": "get",
    "assist": "help",
    "require": "need",
    "indicate": "suggest",
}

CONNECTOR_HEADS_ZH = ("此外，", "同时，", "因此，", "然而，", "与此同时，")


def _sub_cliches(text: str, kind: str) -> tuple[str, list[str]]:
    reasons = []
    table = CLICHE_EN if kind == "en" else CLICHE_ZH
    for k in sorted(table, key=len, reverse=True):
        if k in text:
            text = text.replace(k, table[k])
            reasons.append(f"套话改写：「{k}」→「{table[k]}」")
    return text, reasons


def _sub_synonyms(text: str, kind: str) -> tuple[str, list[str]]:
    reasons = []
    if kind == "en":
        count = 0

        def repl(m):
            nonlocal count
            count += 1
            return SYN_EN[m.group(0).lower()]

        pattern = re.compile(r"\b(" + "|".join(SYN_EN) + r")\b", re.I)
        new = pattern.sub(repl, text)
        if count:
            reasons.append(f"同义替换 {count} 处（打散原文指纹）")
        return new, reasons
    hits = [k for k in SYN_ZH if k in text]
    for k in hits:
        text = text.replace(k, SYN_ZH[k])
    if hits:
        reasons.append(f"同义替换：{'、'.join(hits[:4])}{'…' if len(hits) > 4 else ''}")
    return text, reasons


def _split_long(text: str, kind: str) -> tuple[str, list[str]]:
    """长句切分：改变句长节奏（降 AI 的句长均匀度、打散查重连续串）。"""
    reasons = []
    if kind == "zh":
        units = len(segmenter.normalize(text, "zh"))
        if units >= 34 and text.count("，") >= 2:
            commas = [m.start() for m in re.finditer("，", text)]
            target = min(commas, key=lambda p: abs(p - len(text) * 0.45))
            if 6 < target < len(text) - 6:
                text = text[:target] + "。" + text[target + 1 :]
                reasons.append("长句切分（改变句长节奏）")
    else:
        if len(text.split()) >= 26 and "; " in text:
            text = text.replace("; ", ". ", 1)
            reasons.append("分号改句号（长句切分）")
    return text, reasons


def _thin_connector(text: str, seen: set) -> tuple[str, set, list[str]]:
    """连接词稀释：句首套式连接词只保留首次出现，其后删除。"""
    for head in CONNECTOR_HEADS_ZH:
        if text.startswith(head):
            if head in seen:
                return text[len(head) :], seen, [f"删除句首套式连接词「{head}」"]
            seen.add(head)
            break
    return text, seen, []


def rewrite(text: str, mode: str = "both") -> dict:
    """mode: dedup / humanize / both"""
    do_dedup = mode in ("dedup", "both")
    do_humanize = mode in ("humanize", "both")
    lang = segmenter.detect_language(text)

    # 改写目标定位
    matched_starts: set[int] = set()
    high_starts: set[int] = set()
    before_plag = before_aigc = None
    if do_dedup and CORPUS.docs:
        plag = plag_run(text, {"strip_references": False})
        before_plag = plag["total_rate"]
        matched_starts = {r["start"] for r in plag["sent_results"] if r["matched"]}
    if do_humanize:
        aigc = local_engine.analyze(text, lang)
        before_aigc = aigc["total_rate"]
        high_starts = {s["start"] for s in aigc["sentence_scores"] if s["level"] in ("high", "mid")}

    sents = segmenter.split_sentences(text)
    seen_connectors: set = set()
    segments: list[dict] = []
    edits: list[tuple[int, int, str]] = []

    for s in sents:
        new = s.text
        reasons: list[str] = []
        if do_humanize and s.start in high_starts:
            new, r1 = _sub_cliches(new, s.kind)
            new, seen2, r2 = _thin_connector(new, seen_connectors)
            seen_connectors = seen2
            reasons += r1 + r2
        if do_dedup and s.start in matched_starts:
            new, r3 = _sub_synonyms(new, s.kind)
            new, r4 = _split_long(new, s.kind)
            reasons += r3 + r4
        elif do_humanize and s.start in high_starts and not do_dedup:
            new, r4 = _split_long(new, s.kind)
            reasons += r4
        new = new.strip()
        if reasons and new and new != s.text.strip():
            segments.append(
                {
                    "start": s.start,
                    "end": s.end,
                    "orig": s.text,
                    "new": new,
                    "reasons": reasons,
                }
            )
            edits.append((s.start, s.end, new))

    # 按偏移从后往前替换，得到改写后全文
    full = text
    for start, end, new in sorted(edits, key=lambda e: -e[0]):
        full = full[:start] + new + full[end:]

    # 复测
    after_plag = after_aigc = None
    if before_plag is not None and CORPUS.docs:
        after_plag = plag_run(full, {"strip_references": False})["total_rate"]
    if before_aigc is not None:
        after_aigc = local_engine.analyze(full, lang)["total_rate"]

    return {
        "mode": mode,
        "language": lang,
        "sentence_count": len(sents),
        "changed_count": len(segments),
        "before": {"plagiarism": before_plag, "aigc": before_aigc},
        "after": {"plagiarism": after_plag, "aigc": after_aigc},
        "segments": segments,
        "full_text": full,
        "note": "规则改写引擎：表达层同义替换、套话改写与句式变换，改动均给出理由供人工复核",
    }
