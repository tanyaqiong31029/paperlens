"""分句、语言识别、文本归一化与 n-gram 指纹。

单位约定：中文以"字"为单位，英文以"词"为单位。
归一化只保留 [汉字/字母/数字]，用于指纹比对；原文片段保留用于报告展示。
"""
import re
from dataclasses import dataclass

from .. import config

ZH_END = "。！？；!?;"
_ZH_RE = re.compile(r"[。！？；!?;]")
_EN_SENT_RE = re.compile(r"[^.!?\n]+[.!?]?")
_KEEP_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")
_EN_WORD_RE = re.compile(r"[A-Za-z0-9']+")


@dataclass
class Sentence:
    start: int          # 原文偏移
    end: int
    text: str           # 原句
    units: int          # 字数（中文）或词数（英文）
    norm: str           # 归一化串（中文）或空格连接的小写词（英文）
    kind: str           # zh / en


def detect_language(text: str) -> str:
    zh = len(re.findall(r"[\u4e00-\u9fff]", text))
    en = len(re.findall(r"[A-Za-z]", text))
    if zh == 0 and en == 0:
        return "zh"
    return "zh" if zh >= en else "en"


def normalize(text: str, kind: str) -> str:
    if kind == "zh":
        # 中文：仅保留汉字/字母/数字，去掉空白与标点
        return "".join(_KEEP_RE.findall(text))
    # 英文：小写词序列（词间保留空格，供词级 n-gram 与子串比对使用）
    return " ".join(_EN_WORD_RE.findall(text.lower()))


def split_sentences(text: str) -> list[Sentence]:
    """中英混排通用分句：按中英文终止标点切分，保留原文偏移。"""
    sents: list[Sentence] = []
    start = 0
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if ch in ZH_END:
            _push(sents, text, start, i + 1)
            start = i + 1
        elif ch in ".!?" and (i + 1 == n or text[i + 1] in " \t\n\r\"')】」）》" or not text[i + 1].isalnum()):
            _push(sents, text, start, i + 1)
            start = i + 1
        elif ch == "\n":
            # 空行或换行作为软边界：把换行前残余推出去
            seg = text[start:i]
            if seg.strip():
                sents.append(_build(text, start, i))
            start = i + 1
        i += 1
    if start < n and text[start:].strip():
        sents.append(_build(text, start, n))
    return [s for s in sents if s.text.strip()]


def _push(sents: list[Sentence], text: str, start: int, end: int) -> None:
    if text[start:end].strip():
        sents.append(_build(text, start, end))


def _build(text: str, start: int, end: int) -> Sentence:
    raw = text[start:end]
    kind = detect_language(raw)
    norm = normalize(raw, kind)
    units = len(norm) if kind == "zh" else len(norm.split()) if norm else 0
    return Sentence(start=start, end=end, text=raw, units=units, norm=norm, kind=kind)


def shingles(sent: Sentence, kind: str | None = None) -> set[str]:
    """句子级 shingle 集合：中文按字、英文按词。"""
    kind = kind or sent.kind
    if sent.units < config.MIN_SENT_UNITS:
        return set()
    return shingles_norm(sent.norm, kind)


def shingles_norm(norm: str, kind: str) -> set[str]:
    """对归一化文本直接计算 shingle 集合（联网核查比对复用）。"""
    if not norm:
        return set()
    if kind == "zh":
        n = config.ZH_SHINGLE
        if len(norm) < n:
            return {norm} if len(norm) >= 4 else set()
        return {norm[i: i + n] for i in range(len(norm) - n + 1)}
    n = config.EN_SHINGLE
    words = norm.split()
    if len(words) < n:
        return {" ".join(words)} if len(words) >= 4 else set()
    return {" ".join(words[i: i + n]) for i in range(len(words) - n + 1)}


def similarity(query: set[str], cand: set[str]) -> float:
    """containment：命中比例以较小集合为分母，短句不易被稀释。"""
    if not query or not cand:
        return 0.0
    inter = len(query & cand)
    return inter / min(len(query), len(cand))
