"""AIGC 检测固定评测集评估：AUROC / 最佳F1 / 各阈值FPR。

用法：
    python scripts/eval_aigc.py          # 只用内置自建语料训练 LM（确定性好，CI 可复现）
评测集：backend/evals/aigc_eval.json（自建 24 条中英样本，仅用于回归监控，非学术基准）。
"""
import json
import os
import sys
from pathlib import Path

# 固定数据目录 → 只种子内置语料，保证本地与 CI 结果一致
os.environ.setdefault("PAPERLENS_DATA_DIR", str(Path(__file__).resolve().parent.parent / "evals" / "data"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db                                   # noqa: E402
from app.services.aigc import local_engine           # noqa: E402
from app.services.corpus import CORPUS               # noqa: E402
from app.services import ngram_lm, segmenter         # noqa: E402


def auroc(scores_pos: list[float], scores_neg: list[float]) -> float:
    """秩和法 AUROC（含并列处理）。"""
    items = [(s, 1) for s in scores_pos] + [(s, 0) for s in scores_neg]
    items.sort(key=lambda x: x[0])
    n1, n0 = len(scores_pos), len(scores_neg)
    ranks = {}
    i = 0
    while i < len(items):
        j = i
        while j + 1 < len(items) and items[j + 1][0] == items[i][0]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1
    r1 = sum(ranks[k] for k, (_, lab) in enumerate(items) if lab == 1)
    return (r1 - n1 * (n1 + 1) / 2) / (n1 * n0)


def f1_at(scores: list[tuple[float, int]], th: float) -> tuple[float, float, float]:
    tp = sum(1 for s, y in scores if s >= th and y == 1)
    fp = sum(1 for s, y in scores if s >= th and y == 0)
    fn = sum(1 for s, y in scores if s < th and y == 1)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    fpr = fp / max(1, sum(1 for _, y in scores if y == 0))
    return f1, prec, fpr


def main() -> None:
    db.init_db()
    # 种子内置自建语料（与 main.py 启动逻辑一致），保证 LM 信号参与且结果可复现
    if not db.all_docs_full():
        seed_dir = Path(__file__).resolve().parent.parent / "seed_corpus"
        for f in sorted(seed_dir.glob("*.json")):
            for d in json.loads(f.read_text(encoding="utf-8")):
                db.add_doc(d["title"], d["content"], len(d["content"]), is_builtin=True)
    CORPUS.rebuild()
    ngram_lm.rebuild_lm()

    eval_path = Path(__file__).resolve().parent.parent / "evals" / "aigc_eval.json"
    items = json.loads(eval_path.read_text(encoding="utf-8"))["items"]

    scored = []
    for it in items:
        lang = it["lang"]
        r = local_engine.analyze(it["text"], lang)
        scored.append((r["total_rate"], 1 if it["label"] == "ai" else 0, lang))

    print(f"LM ready: {ngram_lm.LM.ready}  样本数: {len(scored)}\n")

    rows = ["| 子集 | AUROC | 最佳F1(阈值) | FPR@45 | FPR@70 |", "|---|---|---|---|---|"]
    for name, subset in [("全部", scored),
                         ("中文", [s for s in scored if s[2] == "zh"]),
                         ("英文", [s for s in scored if s[2] == "en"])]:
        pos = [s for s, y, _ in subset if y == 1]
        neg = [s for s, y, _ in subset if y == 0]
        auc = auroc(pos, neg)
        best_f1, best_th = 0.0, 50.0
        for th in range(5, 96, 5):
            f1, _, _ = f1_at([(s, y) for s, y, _ in subset], th)
            if f1 > best_f1:
                best_f1, best_th = f1, th
        _, _, fpr45 = f1_at([(s, y) for s, y, _ in subset], 45)
        _, _, fpr70 = f1_at([(s, y) for s, y, _ in subset], 70)
        rows.append(f"| {name} | {auc:.3f} | {best_f1:.3f} ({best_th}) | {fpr45:.2f} | {fpr70:.2f} |")
        print(rows[-1])

    Path(__file__).resolve().parent.parent.joinpath("evals").mkdir(exist_ok=True)
    print("\n（自建小样本，与内置语料同源，用于回归监控；不能作为检测精度的学术结论。）")


if __name__ == "__main__":
    main()
