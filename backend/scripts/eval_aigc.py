"""AIGC 检测固定评测集评估：AUROC / 最佳F1 / 各阈值FPR，可设质量门槛。

用法：
    python scripts/eval_aigc.py                          # 仅打印指标
    python scripts/eval_aigc.py --min-auroc 0.80 --max-fpr45 0.40
                                                         # 指标不达标时退出码 1（CI 用）

评测集：backend/evals/aigc_eval.json（自建 24 条中英样本，仅用于回归监控）。
局限：样本与内置语料同源、AI 样本套话特征明显，指标不能代表真实检测精度；
后续应补充更难的正式论文、人工润色 AI 文本、非母语作者与跨领域文本。
"""

import argparse
import json
import os
import sys
from pathlib import Path

# 固定数据目录 → 只种子内置语料，保证本地与 CI 结果一致
os.environ.setdefault(
    "PAPERLENS_DATA_DIR", str(Path(__file__).resolve().parent.parent / "evals" / "data")
)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.services import ngram_lm  # noqa: E402
from app.services.aigc import local_engine  # noqa: E402
from app.services.corpus import CORPUS  # noqa: E402


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
    ap = argparse.ArgumentParser(description="AIGC 检测回归评测")
    ap.add_argument("--min-auroc", type=float, default=0.0, help="AUROC 门槛，低于则退出码 1")
    ap.add_argument("--max-fpr45", type=float, default=1.0, help="FPR@45 上限，超出则退出码 1")
    args = ap.parse_args()

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
    metrics = {}
    for name, subset in [
        ("全部", scored),
        ("中文", [s for s in scored if s[2] == "zh"]),
        ("英文", [s for s in scored if s[2] == "en"]),
    ]:
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
        rows.append(
            f"| {name} | {auc:.3f} | {best_f1:.3f} ({best_th}) | {fpr45:.2f} | {fpr70:.2f} |"
        )
        print(rows[-1])
        metrics[name] = (auc, fpr45)

    print("\n（自建小样本，与内置语料同源，用于回归监控；不能作为检测精度的学术结论。）")

    # 质量门槛：任一不达标 → 退出码 1（CI 失败）
    overall_auc, overall_fpr45 = metrics["全部"]
    failures = []
    if overall_auc < args.min_auroc:
        failures.append(f"AUROC {overall_auc:.3f} < {args.min_auroc}")
    if overall_fpr45 > args.max_fpr45:
        failures.append(f"FPR@45 {overall_fpr45:.2f} > {args.max_fpr45}")
    if failures:
        print("\n[FAIL] 质量门槛未达标：" + "；".join(failures), file=sys.stderr)
        sys.exit(1)
    if args.min_auroc or args.max_fpr45 < 1.0:
        print("\n[OK] 质量门槛达标")


if __name__ == "__main__":
    main()
