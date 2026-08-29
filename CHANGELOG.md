# 更新日志

本项目的所有重要变更记录于此文件。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本遵循语义化版本。

## [1.1.0] - 2026-08-30

### 安全

- 默认绑定 `127.0.0.1`，仅本机可访问；绑定非回环地址强制要求 `PAPERLENS_ADMIN_TOKEN`
- 管理员令牌接入前端：请求统一经 `apiFetch()` 注入 `X-Admin-Token` 请求头，
  401 时自动弹出令牌输入框；令牌仅存 sessionStorage，关闭标签页即清除；
  移除 query-string 传令牌的兼容方式（避免令牌进入历史/代理日志/Referer）
- CORS 默认关闭（同源部署天然可用），跨域需显式设置 `PAPERLENS_ALLOW_ORIGINS`
- 请求体上限改为 ASGI 网络层中间件（按实际接收字节计数，覆盖 multipart/JSON/
  分块传输与全部上传接口，含文档库），默认 40MB，可用 `PAPERLENS_MAX_BODY_BYTES` 调整
- 检测任务改为有界线程池（并发 2）；采集任务并发上限 2（超出返回 429）

### 隐私

- 提交页按启用状态显示第三方数据流向提示（接收方 + 发送范围）
- README 明确：默认本地模式正文不出设备；GPTZero 发送 ≤30,000 字符；
  联网核查发送归一化检索片段；不再使用绝对化表述
- CopyLeaks 降级为实验性：需 邮箱+Key 双凭据接入，当前不真实调用、不发送数据

### 质量

- 修复依赖审计告警：vite ^6.4.3、react-router-dom ^7.18.3（npm audit 清零）
- 后端依赖锁定精确版本；新增 requirements-dev.txt（pytest / httpx）
- 新增 25 个后端测试（分句/指纹/查重口径/参考文献剥离/docx 解析/报告导出/
  改写/API 冒烟/令牌门禁/请求体上限/令牌全流程 E2E）
- 新增 AIGC 固定评测集（24 条中英样本）与 AUROC/F1/FPR 评估脚本，
  支持 `--min-auroc` / `--max-fpr45` 质量门槛（CI 强制）
- 新增 GitHub Actions CI：后端测试 + 评测 + 前端构建 + 依赖审计
- 安装（setup.sh，npm ci）与启动（start.sh，默认 127.0.0.1）脚本分离

## [1.0.0] - 2026-08-29

### 能力

- 📄 文档查重：句子级 n-gram 指纹 + 倒排索引 + containment 比对（中英双粒度，自动剥离参考文献）
- 🌐 联网核查：OpenAlex / arXiv / Europe PMC 学术库直查 + 搜索引擎链，独立联网重复率
- 🕷️ OA 语料采集：arXiv / OpenAlex（中英）/ DOAJ / Europe PMC 官方 API 增量扩库
- 🤖 AIGC 检测 v2：六维统计指纹 + 语料库 n-gram LM 平滑度信号集成
- ⚖️ 多引擎对比：GPTZero（填 Key 调用）+ transformers 模型插件 + 机构引擎状态标注
- ✂️ 降重 · 降AIGC：规则改写引擎，逐句理由 + 前后复测对比
- 📊 知网式报告：全文三色标红、片段对照、独立 HTML 导出
