"""联网核查（webcheck）异常路径测试：超时/检索失败/页面抓取失败全部降级不炸。"""

from app.services import webcheck


def test_match_in_page_exact_substring():
    sent = {"kind": "zh", "norm": "卷积神经网络能够有效提取图像的局部特征和全局语义信息"}
    page = "背景介绍。卷积神经网络能够有效提取图像的局部特征和全局语义信息，这是该方法的核心优势。结尾。"
    m = webcheck._match_in_page(sent, "卷积神经网络能够有效提取图像的局部特征", page)
    assert m and m["sim"] == 1.0


def test_match_in_page_no_hit():
    sent = {"kind": "zh", "norm": "完全无关的内容主题句子在这里"}
    page = "页面内容与查询完全不同，讨论的是另一个话题。"
    assert webcheck._match_in_page(sent, "完全无关的内容主题句子", page) is None


def test_extract_text_strips_scripts():
    html = "<html><head><style>x{}</style></head><body><script>alert(1)</script><p>正文内容在这里</p></body></html>"
    text = webcheck.extract_text(html)
    assert "正文内容在这里" in text
    assert "alert" not in text and "x{}" not in text


def test_run_all_providers_fail_degrades(monkeypatch):
    """所有检索源失败 → status=error、不抛异常、审计字段齐全。"""
    sents = [
        {
            "start": 0,
            "end": 10,
            "text": "某个足够长的研究性句子用来做联网核查测试之用",
            "units": 20,
            "norm": "某个足够长的研究性句子用来做联网核查测试之用",
            "kind": "zh",
            "matched": False,
        },
    ]
    import app.main  # noqa: F401 确保服务模块已加载

    def boom(*args, **kwargs):
        raise RuntimeError("网络不可达")

    # run() 从 _PROVIDER_FN 表取函数，必须 patch 表而非模块属性
    monkeypatch.setattr(webcheck, "_PROVIDER_FN", {k: boom for k in webcheck._PROVIDER_FN})
    monkeypatch.setattr(webcheck.time, "sleep", lambda s: None)
    r = webcheck.run(sents, {"web_check_count": 3, "web_check_budget": 5})
    assert r["status"] == "error"
    assert r["checked"] == 0 and r["hits"] == []
    assert "失败" in r["note"]


def test_run_hit_records_source(monkeypatch):
    """学术源命中：直接用 provider 自带摘要比对，不抓页面；命中记录 via/url。"""
    sents = [
        {
            "start": 0,
            "end": 10,
            "text": "卷积神经网络能够有效提取图像的局部特征和全局语义信息",
            "units": 22,
            "norm": "卷积神经网络能够有效提取图像的局部特征和全局语义信息",
            "kind": "zh",
            "matched": False,
        },
    ]
    fake = [
        {
            "url": "https://doi.org/10.0000/fake",
            "title": "假想论文",
            "text": "标题\n卷积神经网络能够有效提取图像的局部特征和全局语义信息，这是核心结论。",
        }
    ]
    monkeypatch.setattr(
        webcheck, "_PROVIDER_FN", {**webcheck._PROVIDER_FN, "openalex": lambda q, kind: fake}
    )
    monkeypatch.setattr(webcheck.time, "sleep", lambda s: None)
    r = webcheck.run(sents, {"web_check_count": 3, "web_check_budget": 10})
    assert r["status"] == "ok"
    assert len(r["hits"]) == 1
    assert r["hits"][0]["url"] == "https://doi.org/10.0000/fake"
    assert r["web_dup_rate"] > 0
