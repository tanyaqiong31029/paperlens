"""全局配置：路径、检测参数、AIGC 引擎清单。

安全相关（均可被环境变量覆盖）：
- PAPERLENS_DATA_DIR   数据目录（默认 backend/data）
- PAPERLENS_ADMIN_TOKEN  设置后，/api 下除 health/stats/engines 外的接口
  都要求请求头 X-Admin-Token 匹配；start.sh 仅在绑定非回环地址时要求配置
- PAPERLENS_ALLOW_ORIGINS  逗号分隔的 CORS 白名单；默认不启用 CORS
  （同源部署天然可用），即默认只允许自身地址
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent   # backend/
DATA_DIR = Path(os.environ.get("PAPERLENS_DATA_DIR") or (BASE_DIR / "data"))
DB_PATH = DATA_DIR / "app.db"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"

APP_NAME = "PaperLens 论文检测中心"
APP_VERSION = "1.2.0"
MAX_UPLOAD_MB = 15
MAX_TEXT_CHARS = 2_000_000             # 粘贴正文上限（字符）

ADMIN_TOKEN = os.environ.get("PAPERLENS_ADMIN_TOKEN", "").strip()
MAX_BODY_BYTES = int(os.environ.get("PAPERLENS_MAX_BODY_BYTES", str(40 * 1024 * 1024)))
RETENTION_DAYS = int(os.environ.get("PAPERLENS_RETENTION_DAYS", "0"))  # 0=永久保留

# ---------- 查重参数 ----------
# 中文按"字"为最小单位，英文按"词"。指纹 shingle 长度参考开源
# paper_checking_system 的连续串阈值（13 字左右）拆成两级：
# 短 shingle 负责召回，句子级精确比对负责确准。
ZH_SHINGLE = 8          # 中文 shingle：8 个汉字
EN_SHINGLE = 6          # 英文 shingle：6 个词
ZH_SIM_THRESHOLD = 0.30  # 句子判定为相似的 containment 阈值（中文）
EN_SIM_THRESHOLD = 0.25  # 英文阈值（词粒度更抖，放宽）
MIN_SENT_UNITS = 6       # 短于该单位数的句子不参与相似判定（中文 6 字 / 英文 6 词）
FRAG_MERGE_GAP = 1       # 相似句之间最多隔几个未命中句仍合并为同一片段

# ---------- AIGC 检测 ----------
AIGC_HIGH = 70   # 句级得分 >= 70 判为"高度疑似 AI 生成"
AIGC_MID = 45    # >= 45 判为"疑似"

# ---------- 外部 AIGC 引擎 ----------
# 有公开 API、可自行填 key 直连的引擎；其余主流产品（知网/维普/万方/朱雀/
# Turnitin）为机构接口，无公开 API，仅在报告中列出作为对接说明。
# 注意：调用外部引擎会把正文（或其前缀）发送给对应服务商，提交页会如实提示。
EXTERNAL_ENGINES = {
    "gptzero": {
        "name": "GPTZero",
        "region": "国际",
        "desc": "国际主流 AI 检测服务，支持逐句 AI 概率（调用时发送正文前 ≤30,000 字符）",
        "adapter": "gptzero",
    },
}
# 实验性 / 未完成：CopyLeaks 需要 邮箱 + API Key 双凭据且接口有异步审核流程，
# 当前仅占位，不在检测中真实调用。
EXPERIMENTAL_ENGINES = {
    "copyleaks": {
        "name": "CopyLeaks AI Detector",
        "region": "国际",
        "desc": "实验性：需 邮箱+Key 双凭据接入，暂不可用；正式支持后将明确标注发送范围",
    },
}
INFO_ONLY_ENGINES = [
    {"key": "cnki", "name": "知网 AIGC 检测", "region": "国内",
     "desc": "高校官方定稿系统，仅对高校/机构开放，无公开 API"},
    {"key": "wanfang", "name": "万方 AIGC 检测", "region": "国内",
     "desc": "万方数据 AIGC 检测服务，接口需商务对接"},
    {"key": "vip", "name": "维普 AIGC 检测", "region": "国内",
     "desc": "维普论文检测附属功能，接口需商务对接"},
    {"key": "zhuque", "name": "腾讯朱雀实验室", "region": "国内",
     "desc": "AI 生成文本检测工具，暂无公开 API"},
    {"key": "turnitin", "name": "Turnitin AI Writing", "region": "国际",
     "desc": "国际高校主流，仅随机构订阅提供，无独立公开 API"},
]

# ---------- 联网核查检索源 ----------
# Bing API / SerpAPI 配置 Key 后优先使用；未配置时用 Bing/DuckDuckGo 网页检索兜底。
SEARCH_PROVIDERS = {
    "bing_api": {
        "name": "Bing Search API",
        "desc": "微软必应官方检索 API，稳定可靠，Azure 按量计费",
        "docs": "https://www.microsoft.com/bing/apis",
    },
    "serpapi": {
        "name": "SerpAPI（Google）",
        "desc": "聚合 Google 检索结果的第三方 API，按量计费",
        "docs": "https://serpapi.com",
    },
}

for _d in (DATA_DIR, UPLOAD_DIR, EXPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)
