# 关于 PaperLens

**PaperLens 论文检测中心**是一个本地部署的论文查重 + AIGC 检测平台。

- 🔍 **查重**：句子级 n-gram 指纹 + 倒排索引，IDF 双门槛压误报，规范引用独立口径
- 🤖 **AIGC 检测**：六维统计指纹 + 语料库 n-gram LM 平滑度信号，多引擎对比
- 🌐 **联网核查**：OpenAlex / arXiv / Europe PMC 学术库直查 + 搜索引擎兜底
- ✂️ **降重·降AIGC**：逐句改写建议 + 自动复测
- 🔒 **默认本地检测**：不开外部引擎，论文不出电脑

## 文档导航

| 文档 | 内容 |
|---|---|
| [README.md](README.md) | 功能总览、快速开始、算法方法、隐私与数据流向 |
| [README_EN.md](README_EN.md) | English overview |
| [CHANGELOG.md](CHANGELOG.md) | 版本变更记录 |
| [SECURITY.md](SECURITY.md) | 安全模型、漏洞报告通道 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 参与贡献流程与约定 |

## 仓库概况

- 后端：FastAPI + SQLite（`backend/`），索引快照温启动、有界任务队列、SSE 进度流
- 前端：React 18 + Vite + Tailwind（`frontend/`），令牌感知、降重对比、多引擎报告
- 测试：pytest 54+ 用例 · CI 含覆盖率、mypy/ruff、gitleaks、npm/pip 审计
