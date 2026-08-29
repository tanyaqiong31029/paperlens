"""本地 AIGC 统计检测引擎 v2（离线多信号集成）。

方法演进（详见 README「AIGC 检测方法」小节）：
- v1：LLM 文本的六维统计指纹（句长均匀、套话密度、连接词规整、词汇中庸、
  标点单一、句式模板化），对应 GPTZero 早期 perplexity+burstiness 一脉的思路；
- v2（当前）：引入语料库三元语法 LM 的两个**平滑度信号**——句间突发性
  （各句困惑度的变异系数）与 token 级困惑波动，与六特征加权集成。方法上
  呼应 DetectGPT(ICLR'23) / Fast-DetectGPT(ICLR'24) / Binoculars(ICML'24)
  的核心观察：机器文本在语言模型下"更可预测、更平滑"。注意我们刻意不使用
  绝对困惑度：校准实测发现域内 LM 对域内人类学术文本的 ppl 反而更低
  （领域自适应效应），波动形状才是跨域稳定的信号。n-gram LM 是神经 LM 的
  轻量替身，对改写鲁棒性弱于神经模型，故仅占部分权重，最终判定鼓励多引擎
  交叉验证。
- 输出：全文级 + 句子级 AI 疑似度 + 八维特征雷达；段落级风险聚合。
"""
import math
import re

from ... import config
from .. import segmenter, ngram_lm

ZH_CONNECTORS = [
    "因此", "然而", "此外", "同时", "综上所述", "总而言之", "首先", "其次",
    "再次", "最后", "一方面", "另一方面", "值得注意的是", "与此同时",
    "更重要的是", "不仅如此", "随着", "基于此", "由此可见", "换句话说",
]
ZH_CLICHES = [
    "具有重要意义", "重要的理论意义", "实践意义", "奠定坚实基础", "提供有力支持",
    "发挥着重要作用", "发挥重要作用", "广泛应用", "深入研究", "不断涌现",
    "日益增长", "密切相关", "取得显著成效", "有效提升", "不断优化", "日趋完善",
    "提供了新的思路", "新的机遇和挑战", "可持续发展", "高质量发展", "深度融合",
    "助力", "赋能", "全方位", "多层次", "多角度", "深入探讨", "进行了系统",
    "进行了深入研究", "旨在", "本文将从", "综上所述", "值得注意的是",
    "需要指出的是", "不难发现", "由此可见", "显而易见",
]
EN_CONNECTORS = [
    "however", "moreover", "furthermore", "additionally", "in conclusion",
    "overall", "therefore", "thus", "firstly", "secondly", "thirdly",
    "nevertheless", "in addition", "on the other hand", "in summary",
    "consequently", "as a result", "for instance", "for example", "notably",
]
EN_CLICHES = [
    "it is important to note", "plays a crucial role", "plays a vital role",
    "in today's", "delve into", "leverage", "comprehensive understanding",
    "a testament to", "ever-evolving", "navigate the", "foster",
    "underscore", "pave the way", "significant impact", "in the realm of",
    "it is worth noting", "landscape of", "multifaceted", "robust",
    "seamless", "holistic", "paradigm shift", "cutting-edge", "in summary",
]

# 平滑度映射锚点（由对照样本校准测得，见 docs/ 方法说明）：
# 句间突发性：AI ≈0.18，人类 0.31–0.53；token 级：AI ≈0.14，人类 0.18–0.33。
# 注：不使用绝对困惑度——域内 LM 对域内人类学术文本 ppl 反而更低（校准实测），
# "波动形状"（平滑度）才是跨域稳定的信号。
_BURST_ANCHOR = {"sent": 0.50, "token": 0.32}


def _safe(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _burst_ai_score(burst: float, anchor: float) -> float:
    """低突发性/低平滑波动 → 高 AI 分。"""
    return _safe(1 - burst / anchor, 0.0, 1.0)


def analyze(text: str, lang: str) -> dict:
    sents = [s for s in segmenter.split_sentences(text) if s.units >= 3]
    if not sents:
        return _empty()

    lm = ngram_lm.LM
    lm_ready = lm.ready

    # ---- 全文统计特征 ----
    lens = [s.units for s in sents]
    mean_len = sum(lens) / len(lens)
    var = sum((l - mean_len) ** 2 for l in lens) / len(lens)
    cv = math.sqrt(var) / mean_len if mean_len else 0

    low = text.lower()
    connectors = ZH_CONNECTORS if lang == "zh" else EN_CONNECTORS
    cliches = ZH_CLICHES if lang == "zh" else EN_CLICHES
    conn_hits = sum(low.count(c) for c in connectors) if lang == "en" else sum(text.count(c) for c in connectors)
    cliche_hits = sum(low.count(c) for c in cliches) if lang == "en" else sum(text.count(c) for c in cliches)
    conn_density = conn_hits / len(sents)
    cliche_density = cliche_hits / len(sents)

    if lang == "zh":
        chars = list(segmenter.normalize(text, "zh"))
        ttr = (len(set(chars)) or 1) / max(1, len(chars))
        ttr_score = 1 - abs(ttr - 0.52) / 0.25
    else:
        words = segmenter.normalize(text, "en").split()
        ttr = (len(set(words)) or 1) / max(1, len(words))
        ttr_score = 1 - abs(ttr - 0.42) / 0.30

    puncts = re.findall(r"[,;:!?()【】《》“”‘’、——…]", text)
    punct_score = 1 - _safe(len(set(puncts)) / 12, 0, 1)

    heads = [s.text[:2] for s in sents]
    head_div = len(set(heads)) / len(heads)

    # ---- LM 平滑度信号（句间突发性 + token 级平滑波动；不用绝对 ppl，见锚点注释）----
    s_ppls: list[float] = []
    t_vals: list[float] = []
    if lm_ready:
        for s in sents:
            r = lm.sentence_stats(s.norm, s.kind)
            if r and r[0] > 0:
                s_ppls.append(r[0])
            tb = lm.token_burst(s.norm, s.kind)
            if tb is not None:
                t_vals.append(tb)
    sent_burst_score = None
    token_burst_score = None
    if len(s_ppls) >= 3:
        mean_p = sum(s_ppls) / len(s_ppls)
        if mean_p > 0:
            cv_p = math.sqrt(sum((x - mean_p) ** 2 for x in s_ppls) / len(s_ppls)) / mean_p
            sent_burst_score = _burst_ai_score(cv_p, _BURST_ANCHOR["sent"])
    if len(t_vals) >= 2:
        token_burst_score = _burst_ai_score(sum(t_vals) / len(t_vals), _BURST_ANCHOR["token"])

    # ---- 全文集成 ----
    z = (
        1.4 * (1 - _safe(cv / 0.55, 0, 1))
        + 0.9 * _safe(conn_density / 0.45, 0, 1.5)
        + 1.4 * _safe(cliche_density / 0.35, 0, 1.5)
        + 0.7 * _safe(ttr_score, 0, 1)
        + 0.6 * punct_score
        + 0.7 * (1 - _safe(head_div, 0, 1)) / 0.6
        - 2.2
    )
    if sent_burst_score is not None:
        z += 0.8 * sent_burst_score
    if token_burst_score is not None:
        z += 0.7 * token_burst_score
    total = round(_sigmoid(z * 1.05) * 100, 1)

    # ---- 句子级打分 ----
    med_tb = sorted(t_vals)[len(t_vals) // 2] if t_vals else None
    sent_scores: list[dict] = []
    for s in sents:
        sl = s.text.lower()
        sh = sum(sl.count(c) for c in cliches) if lang == "en" else sum(s.text.count(c) for c in cliches)
        ch = sum(sl.count(c) for c in connectors) if lang == "en" else sum(s.text.count(c) for c in connectors)
        len_dev = abs(s.units - mean_len) / mean_len if mean_len else 0
        opener = s.text[:2] if lang == "zh" else " ".join(sl.split()[:2])
        is_formula_head = opener in {h for h in heads if heads.count(h) >= 3}
        zc = (
            1.5 * sh
            + 0.6 * ch
            + 0.8 * (1 - _safe(len_dev / 0.7, 0, 1))
            + (0.5 if is_formula_head else 0)
            - 1.1
        )
        if lm_ready and med_tb:
            tb = lm.token_burst(s.norm, s.kind)
            if tb is not None:
                # 句内平滑度显著低于全文中位 → 更"均匀" → AI 信号
                zc += 0.5 * _safe((med_tb - tb) / med_tb / 0.5, 0, 1.2)
        score = round(_sigmoid(zc * 1.4) * 100, 1)
        level = "high" if score >= config.AIGC_HIGH else ("mid" if score >= config.AIGC_MID else "low")
        sent_scores.append({
            "start": s.start, "end": s.end, "text": s.text,
            "score": score, "level": level,
        })

    # 全文最终分 = 字数加权句级均值 ×0.6 + 统计集成 ×0.4
    wsum = sum(x["end"] - x["start"] for x in sent_scores)
    weighted = (sum(x["score"] * (x["end"] - x["start"]) for x in sent_scores) / wsum) if wsum else total
    final = round(weighted * 0.6 + total * 0.4, 1)

    features = {
        "句式均匀度": round((1 - _safe(cv / 0.55, 0, 1)) * 100),
        "套话密度": round(_safe(cliche_density / 0.35, 0, 1.5) * 66),
        "连接词规整度": round(_safe(conn_density / 0.45, 0, 1.5) * 66),
        "词汇中庸度": round(_safe(ttr_score, 0, 1) * 100),
        "标点单一度": round(punct_score * 100),
        "句式模板化": round((1 - _safe(head_div, 0, 1)) * 100 / 0.6),
    }
    if sent_burst_score is not None:
        features["句间平齐度"] = round(sent_burst_score * 100)
    if token_burst_score is not None:
        features["低困惑波动"] = round(token_burst_score * 100)
    features = {k: max(5, min(100, v)) for k, v in features.items()}

    paras = _paragraph_scores(sent_scores)
    return {
        "engine": "本地集成引擎 v2",
        "total_rate": final,
        "sentence_scores": sent_scores,
        "paragraphs": paras,
        "features": features,
        "note": "六维统计指纹 + 语料库 n-gram 困惑度/突发性 多信号集成（离线）",
    }


def _paragraph_scores(sent_scores: list[dict]) -> list[dict]:
    paras: list[dict] = []
    cur: list[dict] = []
    for s in sent_scores:
        if cur and s["start"] - cur[-1]["end"] > 40:
            paras.append(cur)
            cur = []
        cur.append(s)
    if cur:
        paras.append(cur)
    out = []
    for i, group in enumerate(paras):
        rate = round(sum(g["score"] for g in group) / len(group), 1)
        out.append({
            "index": i, "start": group[0]["start"], "end": group[-1]["end"],
            "rate": rate, "high_count": sum(1 for g in group if g["level"] == "high"),
            "count": len(group),
        })
    return out


def _empty() -> dict:
    return {
        "engine": "本地集成引擎 v2", "total_rate": 0.0, "sentence_scores": [],
        "paragraphs": [], "features": {}, "note": "文本过短",
    }
