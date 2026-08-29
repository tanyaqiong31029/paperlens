"""语料库支撑的 n-gram 语言模型：为 AIGC 检测提供困惑度（perplexity）与
突发性（burstiness）信号。

方法脉络（见 README「AIGC 检测方法」）：
- GPTZero 早期方案即 perplexity + burstiness（Tian & Cui 2023）：AI 文本在
  语言模型下困惑度更低、句间分布更均匀；
- DetectGPT(ICLR'23) → Fast-DetectGPT(ICLR'24) 用概率曲率，Binoculars(ICML'24)
  用双模型交叉困惑度，均优于纯统计量——但都需要神经 LM。
本模块用对比库（OA 论文语料）构建字符级（中）/词级（英）三元语法 LM，
作为神经 LM 的轻量替身：领域内低困惑度 + 低突发性 → AI 风险信号之一。
已知局限（诚实声明）：n-gram 困惑度对改写鲁棒性弱于神经 LM，因此本信号
只占集成权重的一部分，不单独定论。
"""
import math
import re
from collections import defaultdict

from .. import config
from . import segmenter

_K = 0.4  # add-k 平滑


class TrigramLM:
    def __init__(self) -> None:
        self.uni = defaultdict(int)
        self.bi = defaultdict(int)
        self.tri = defaultdict(int)
        self.total = 0
        self._ready = False

    def train(self, docs_norm: list[tuple[str, str]]) -> None:
        """docs_norm: [(norm_text, kind)]"""
        for norm, kind in docs_norm:
            toks = self._tokens(norm, kind)
            for t in toks:
                self.uni[t] += 1
            for a, b in zip(toks, toks[1:]):
                self.bi[(a, b)] += 1
            for a, b, c in zip(toks, toks[1:], toks[2:]):
                self.tri[(a, b, c)] += 1
            self.total += max(0, len(toks) - 2)
        self._ready = self.total > 1000

    @staticmethod
    def _tokens(norm: str, kind: str) -> list[str]:
        if kind == "zh":
            return list(norm)
        return norm.split()

    @property
    def ready(self) -> bool:
        return self._ready

    def _p(self, a: str, b: str, c: str) -> float:
        """P(c | a, b)：三元插值二元 + add-k。"""
        tri_ab = self.bi.get((a, b), 0)
        tri_abc = self.tri.get((a, b, c), 0)
        uni_c = self.uni.get(c, 0)
        v = max(len(self.uni), 1)
        p_tri = (tri_abc + _K) / (tri_ab + _K * v) if tri_ab else 0.0
        p_bi = (uni_c + _K) / (self.total + _K * v)
        return 0.6 * p_tri + 0.4 * p_bi

    def sentence_stats(self, norm: str, kind: str) -> tuple[float, float] | None:
        """返回 (困惑度, 突发性)。tok 过少返回 None。"""
        toks = self._tokens(norm, kind)
        if len(toks) < 8 or not self._ready:
            return None
        logs = []
        for a, b, c in zip(toks, toks[1:], toks[2:]):
            logs.append(math.log(max(self._p(a, b, c), 1e-12)))
        if not logs:
            return None
        mean_lp = sum(logs) / len(logs)
        ppl = math.exp(-mean_lp)
        if len(logs) >= 3:
            mean = mean_lp
            var = sum((x - mean) ** 2 for x in logs) / len(logs)
            burst = math.sqrt(var)  # log 概率的标准差
        else:
            burst = 0.0
        return ppl, burst

    def token_burst(self, norm: str, kind: str) -> float | None:
        """token 级平滑度：句内各 token log 概率的变异系数。

        AI 文本 token 间"惊奇度"更平齐 → 值低；人类文本有惊喜峰值 → 值高。
        注意：不用绝对困惑度——域内 LM 对域内人类文本 ppl 反而更低（已实测），
        平滑度（波动形状）才是跨域稳定的信号。
        """
        toks = self._tokens(norm, kind)
        if len(toks) < 8 or not self._ready:
            return None
        logs = [math.log(max(self._p(a, b, c), 1e-12)) for a, b, c in zip(toks, toks[1:], toks[2:])]
        if len(logs) < 3:
            return None
        mean = sum(logs) / len(logs)
        if mean == 0:
            return None
        return math.sqrt(sum((x - mean) ** 2 for x in logs) / len(logs)) / abs(mean)

    def doc_burstiness(self, sents_norm: list[tuple[str, str]]) -> float | None:
        """句级突发性：各句困惑度的变异系数（GPTZero 式 burstiness）。"""
        ppls = []
        for norm, kind in sents_norm:
            r = self.sentence_stats(norm, kind)
            if r:
                ppls.append(r[0])
        if len(ppls) < 3:
            return None
        mean = sum(ppls) / len(ppls)
        if mean <= 0:
            return None
        return math.sqrt(sum((x - mean) ** 2 for x in ppls) / len(ppls)) / mean


LM = TrigramLM()


def rebuild_lm() -> None:
    """服务启动 / 语料变更后重建。从 CORPUS 取归一化文本训练。"""
    from .corpus import CORPUS  # 局部导入避免循环

    docs = []
    for d in CORPUS.docs.values():
        kind = "zh" if any("\u4e00" <= ch <= "\u9fff" for s in d.sentences[:3] for ch in s.norm) else "en"
        norm = " ".join(s.norm for s in d.sentences)
        if len(norm) > 100:
            docs.append((norm, kind))
    LM.train(docs)
