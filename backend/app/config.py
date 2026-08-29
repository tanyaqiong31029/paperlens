"""全局配置：路径、检测参数、AIGC 引擎清单。"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent   # backend/
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "app.db"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"

APP_NAME = "PaperLens 论文检测中心"
APP_VERSION = "1.0.0"
MAX_UPLOAD_MB = 15

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
EXTERNAL_ENGINES = {
    "gptzero": {
        "name": "GPTZero",
        "region": "国际",
        "desc": "国际主流 AI 检测服务，支持逐句 AI 概率",
        "adapter": "gptzero",
    },
    "copyleaks": {
        "name": "CopyLeaks AI Detector",
        "region": "国际",
        "desc": "支持 30+ 语言的企业级 AI 内容检测",
        "adapter": "copyleaks",
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
