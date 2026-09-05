"""本地模型引擎插件位（可选，transformers）。

为「方法升级路线」预留的标准接口，安装依赖后自动启用：
    pip install "transformers>=4.40" torch

模型通过环境变量配置（不设置则用默认值）：
    AIGC_MODEL_EN   英文检测模型，默认 Hello-SimpleAI/chatgpt-detector-roberta
                    （HC3 数据集微调的 RoBERTa 分类器）
    AIGC_MODEL_ZH   中文检测模型，默认 Hello-SimpleAI/chatgpt-qa-detector-roberta-chinese；
                    也可指向自训模型（HC3-Chinese / M4 / NLPCC'25 Task1 DetectRL-ZH
                    基准上的微调权重均可，只要输出 标准 text-classification 接口）。

懒加载：首次检测才 import transformers 与权重；未安装时引擎列表如实显示
"未安装"，不影响其他引擎。分块策略：按句聚合到 ≤380 词/字 的块分别推理，
按字数加权汇总，兼容 512 token 限制。
"""

import os

from .. import segmenter

_DEFAULT_MODELS = {
    "en": "Hello-SimpleAI/chatgpt-detector-roberta",
    "zh": "Hello-SimpleAI/chatgpt-qa-detector-roberta-chinese",
}
_pipes: dict[str, object] = {}


def model_name(lang: str) -> str:
    return os.environ.get(f"AIGC_MODEL_{lang.upper()}", _DEFAULT_MODELS.get(lang, ""))


def is_installed() -> bool:
    try:
        import transformers  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def _get_pipe(lang: str):
    if lang in _pipes:
        return _pipes[lang]
    import transformers

    name = model_name(lang)
    if not name:
        raise RuntimeError(f"未配置 {lang} 检测模型")
    _pipes[lang] = transformers.pipeline(
        "text-classification",
        model=name,
        truncation=True,
        top_k=None,
    )
    return _pipes[lang]


def _ai_prob(pred: list[dict]) -> float:
    """从 top_k 结果里找 AI 标签的概率。"""
    best = 0.0
    for p in pred:
        label = str(p.get("label", "")).lower()
        if any(k in label for k in ("ai", "machine", "generated", "chatgpt", "label_1", "1")):
            best = max(best, float(p.get("score", 0)))
    return best


def _chunks(text: str, kind: str, limit: int = 380) -> list[tuple[str, int]]:
    """按句聚合成 ≤limit 单位的块，返回 [(块文本, 单位数)]。"""
    out: list[tuple[str, int]] = []
    cur, cur_n = [], 0
    for s in segmenter.split_sentences(text):
        if cur_n + s.units > limit and cur:
            out.append((" ".join(cur), cur_n))
            cur, cur_n = [], 0
        cur.append(s.text.strip())
        cur_n += s.units
    if cur:
        out.append((" ".join(cur), cur_n))
    return out if kind == "en" else [(" ".join(t.split()), n) for t, n in out]


def analyze(text: str, lang: str) -> dict:
    if not is_installed():
        raise RuntimeError("transformers 未安装：pip install 'transformers>=4.40' torch")
    pipe = _get_pipe(lang)
    kind = lang
    chunks = _chunks(text, kind)
    if not chunks:
        return {"total_rate": 0.0, "chunks": 0}
    num_units = prob_sum = 0.0
    for chunk_text, units in chunks:
        res = pipe(chunk_text[:4000])[0]
        prob = _ai_prob(res)
        prob_sum += prob * units
        num_units += units
    rate = round(prob_sum / num_units * 100, 1) if num_units else 0.0
    return {"total_rate": rate, "chunks": len(chunks), "model": model_name(lang)}
