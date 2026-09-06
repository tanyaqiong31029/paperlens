# AGENTS.md — AI 协作规范（paperlens）

本项目已接入完整工程化规范（pre-commit 钩子 / ruff / mypy / gitleaks / CI）。AI agent 在本仓库工作时遵守以下约定。

## 项目概要
论文查重 + AIGC 检测自托管服务（Python）：`backend/app/`（FastAPI：services/{plagiarism,corpus,crawler,webcheck,aigc/*}）、`frontend/`、`scripts/eval_aigc.py`（质量门槛回归）。

## 常用命令
```bash
uvx ruff check . && uvx ruff format --check .    # lint（ruff 锚定 0.12.5，保持 0 问题）
uvx mypy .                                       # 类型检查（宽松档，已入 CI，保持 0 错误）
cd backend && uv run --with-requirements requirements.txt \
  --with-requirements requirements-dev.txt --with pytest pytest tests/ -q   # 41 个用例必须全绿
cd backend && uv run --with-requirements requirements.txt \
  python scripts/eval_aigc.py --min-auroc 0.80 --max-fpr45 0.40              # AIGC 质量门槛（基线 AUROC 1.000）
```

## 提交规范
- 提交信息：Conventional Commits（`<type>(<scope>)?: <subject>`），本地 pre-commit 钩子强制校验。
- 钩子改了文件 → `git add -u` 重新提交；**禁止 --no-verify**。
- lint 级修复与功能改动分开提交。

## 行为红线
- **凡改动 `backend/app/services/aigc/**` 或任何检测逻辑，必须先跑 AIGC 质量门槛并通过**（AUROC 不得低于基线）；门槛不过 = 回归破坏，禁止提交。
- 密钥（GPTZero/Bing/SerpAPI 等）只走环境变量或 `backend/data/`（已 gitignore），绝不入库。
- `E501` 已全局豁免：中文注释长行**不要手工折行**。
- ruff 版本锚点 0.12.5（pre-commit 与 CI 已对齐）；升级时三处同步。
- `webcheck.py`/`crawler.py` 为联网模块，改动注意超时与降级路径的容错语义。
