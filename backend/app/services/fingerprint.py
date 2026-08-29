"""SimHash：文档级近似去重指纹（用于语料库管理页的重复文档提示）。"""
import hashlib
from collections import Counter

from .. import config


def _hash64(token: str) -> int:
    return int.from_bytes(hashlib.md5(token.encode()).digest()[:8], "big")


def simhash(norm_text: str, kind: str = "zh") -> int:
    """对归一化文本整体计算 64 位 SimHash。"""
    if kind == "zh":
        grams = [norm_text[i: i + 4] for i in range(max(1, len(norm_text) - 3))]
    else:
        words = norm_text.split()
        grams = [" ".join(words[i: i + 4]) for i in range(max(1, len(words) - 3))]
    if not grams:
        return 0
    weights = Counter(grams)
    bits = [0] * 64
    for g, w in weights.items():
        h = _hash64(g)
        for b in range(64):
            bits[b] += w if (h >> b) & 1 else -w
    out = 0
    for b, v in enumerate(bits):
        if v > 0:
            out |= 1 << b
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def is_near_duplicate(a: int, b: int) -> bool:
    return hamming(a, b) <= 12
