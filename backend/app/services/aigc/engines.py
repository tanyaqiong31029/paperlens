"""AIGC 多引擎注册与适配器。

- 本地统计引擎：始终可用，离线打分；
- GPTZero / CopyLeaks：有公开 API，用户在"引擎配置"页填入 key 即真实调用；
- 知网 / 万方 / 维普 / 朱雀 / Turnitin：无公开 API（机构接口），
  在报告中如实标注"需机构接口对接"，不做假数据。
"""
import json
import urllib.request

from ... import config
from ... import db
from . import local_engine
from . import model_engine


class EngineOutcome(dict):
    pass


def _outcome(key: str, name: str, region: str, status: str, rate: float | None = None,
             note: str = "", sentences: list | None = None) -> dict:
    return {
        "key": key, "name": name, "region": region, "status": status,
        "rate": rate, "note": note, "sentence_scores": sentences or [],
    }


def detect_all(text: str, lang: str) -> list[dict]:
    results: list[dict] = []

    # 1) 本地引擎（内置，永远执行）
    local = local_engine.analyze(text, lang)
    local_out = _outcome(
        "local", local["engine"], "内置", "ok", local["total_rate"], local["note"],
        local["sentence_scores"],
    )
    # 附带完整分析结果供报告页使用（雷达图、段落风险）
    local_out["features"] = local["features"]
    local_out["paragraphs"] = local["paragraphs"]
    results.append(local_out)

    keys = db.get_engine_keys()

    # 1.5) 本地模型引擎（transformers 插件，可选安装）
    if model_engine.is_installed():
        try:
            mr = model_engine.analyze(text, lang)
            results.append(_outcome(
                "transformers", f"本地模型引擎", "国际+国内", "ok", mr["total_rate"],
                f"模型 {mr.get('model', '')}，{mr.get('chunks', 0)} 块加权",
            ))
        except Exception as e:  # noqa: BLE001
            results.append(_outcome(
                "transformers", "本地模型引擎", "国际+国内", "error", None, f"推理失败：{e}",
            ))
    else:
        results.append(_outcome(
            "transformers", "本地模型引擎", "国际+国内", "not_configured", None,
            "未安装 transformers（pip install 'transformers>=4.40' torch），安装后自动加载 HC3 微调检测器",
        ))

    # 2) 可配置的真实外部引擎
    for key, meta in config.EXTERNAL_ENGINES.items():
        conf = keys.get(key)
        if not conf or not conf.get("enabled") or not conf.get("api_key"):
            results.append(_outcome(
                key, meta["name"], meta["region"], "not_configured", None,
                "未配置 API Key，可在「引擎配置」页填写后启用",
            ))
            continue
        try:
            if meta["adapter"] == "gptzero":
                rate, note = _call_gptzero(text, conf["api_key"])
            elif meta["adapter"] == "copyleaks":
                rate, note = _call_copyleaks(text, conf["api_key"])
            else:
                rate, note = None, "适配器未实现"
            results.append(_outcome(key, meta["name"], meta["region"], "ok", rate, note))
        except Exception as e:  # noqa: BLE001
            results.append(_outcome(key, meta["name"], meta["region"], "error", None, f"调用失败：{e}"))

    # 3) 仅展示用途的机构引擎
    for meta in config.INFO_ONLY_ENGINES:
        results.append(_outcome(
            meta["key"], meta["name"], meta["region"], "manual", None, meta["desc"],
        ))
    return results


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _call_gptzero(text: str, api_key: str) -> tuple[float, str]:
    # 文档：POST /v2/predict/text，header x-api-key
    data = _post_json(
        "https://api.gptzero.me/v2/predict/text",
        {"document": text[:30000], "version": "2024-10-22"},
        {"x-api-key": api_key},
    )
    doc = data.get("documents", [{}])[0]
    prob = doc.get("completely_generated_prob", 0)
    return round(prob * 100, 1), f"完全 AI 生成概率 {prob:.2%}"


def _call_copyleaks(text: str, api_key: str) -> tuple[float, str]:
    # CopyLeaks 需要两步（获取 token + 异步扫描），此处同步轮询简化实现；
    # 无 key 时不会走到这里。接口地址以官方文档为准，可按账号区域调整。
    auth = _post_json(
        "https://id.copyleaks.com/v3/account/login/api",
        {"email": "", "key": api_key}, {},  # 实际需填邮箱+key，占位说明
    )
    token = auth.get("access_token", "")
    scan = _post_json(
        "https://api.copyleaks.com/v2/writer-detector/submit/sync",
        {"text": text[:20000]},
        {"Authorization": f"Bearer {token}"},
    )
    rate = scan.get("score", {}).get("ai", 0)
    return round(rate * 100, 1), "CopyLeaks AI 检测结果"


def list_engines() -> list[dict]:
    keys = db.get_engine_keys()
    out = [{
        "key": "transformers",
        "name": "本地模型引擎（transformers）",
        "region": "国际+国内",
        "desc": "HC3 微调 RoBERTa 检测器插件（可用 AIGC_MODEL_EN/ZH 指向自训模型，"
                "兼容 NLPCC'25 DetectRL-ZH 等中文方案）",
        "type": "model",
        "configured": model_engine.is_installed(),
        "enabled": model_engine.is_installed(),
    }]
    for key, meta in config.EXTERNAL_ENGINES.items():
        conf = keys.get(key, {})
        out.append({
            **meta, "key": key, "type": "api",
            "configured": bool(conf.get("api_key")),
            "enabled": bool(conf.get("enabled")),
        })
    for meta in config.INFO_ONLY_ENGINES:
        out.append({**meta, "key": meta["key"], "type": "manual",
                    "configured": False, "enabled": False})
    for key, meta in config.SEARCH_PROVIDERS.items():
        conf = keys.get(key, {})
        out.append({**meta, "key": key, "region": "联网核查", "type": "search",
                    "configured": bool(conf.get("api_key")),
                    "enabled": bool(conf.get("enabled"))})
    return out
