"""查重主流程测试：基于临时库构造语料，验证命中、来源与降噪。"""
import pytest

from app import db
from app.services import plagiarism
from app.services.corpus import CORPUS


@pytest.fixture(scope="module", autouse=True)
def seed_corpus():
    db.init_db()
    doc_a = (
        "深度学习技术在图像识别领域取得了突破性进展。"
        "卷积神经网络能够有效提取图像的局部特征和全局语义信息，在分类任务中表现优异。"
        "这一项完全无关的句子用来撑起篇幅，讲述的是别的事情，不会和查询文本产生任何重合。"
    )
    doc_b = (
        "乡村振兴战略下农村电商发展迅速。"
        "物流体系的完善为农产品上行提供了坚实支撑，带动了农民增收。"
    )
    doc_a_id = db.add_doc("图像识别研究", doc_a, len(doc_a))
    db.add_doc("农村电商观察", doc_b, len(doc_b))
    CORPUS.rebuild()
    yield doc_a_id


def test_copied_text_hits_source():
    query = (
        "本文探讨相关话题。"
        "深度学习技术在图像识别领域取得了突破性进展。"
        "卷积神经网络能够有效提取图像的局部特征和全局语义信息，在分类任务中表现优异。"
    )
    result = plagiarism.run(query, {"strip_references": False})
    assert result["total_rate"] > 30
    assert result["sources"], "应至少命中一个来源"
    assert result["sources"][0]["title"] == "图像识别研究"
    assert result["fragments"], "相似句应合并为片段"


def test_original_text_no_hit():
    query = (
        "量子退相干机制的研究涉及开放量子系统的动力学演化，"
        "本文提出了一种新的主方程近似方法，并在超导量子比特阵列上进行了数值验证。"
    )
    result = plagiarism.run(query, {"strip_references": False})
    assert result["total_rate"] == 0.0
    assert result["fragments"] == []


def test_strip_references_option():
    text = "深度学习技术在图像识别领域取得了突破性进展。\n\n参考文献\n[1] 某某. 某某研究[J]. 2020."
    kept = plagiarism.run(text, {"strip_references": True})
    dropped = plagiarism.run(text, {"strip_references": False})
    # 剥离参考文献后参与比对的字数更少
    assert kept["total_units"] < dropped["total_units"]


def test_same_sentence_counted_once():
    """同一句重复出现多次命中，重复字数按句去重（每句只计一次）。"""
    query = "卷积神经网络能够有效提取图像的局部特征和全局语义信息，在分类任务中表现优异。"
    result = plagiarism.run(query, {"strip_references": False})
    assert result["total_rate"] == pytest.approx(100.0, abs=0.5)


def test_quoted_citation_reduced_from_total_rate():
    """规范引用口径：命中句用引号包裹（≥60%）时计入引用率而非复制比。"""
    raw = "卷积神经网络能够有效提取图像的局部特征和全局语义信息，在分类任务中表现优异。"
    cited = f"原文指出：“{raw}”"
    r_cited = plagiarism.run(cited, {"strip_references": False})
    r_plain = plagiarism.run(raw, {"strip_references": False})
    assert r_plain["quote_rate"] == 0.0
    assert r_cited["quote_rate"] > 30          # 引号内容被识别为规范引用
    assert r_cited["total_rate"] < r_plain["total_rate"]  # 复制比因规范引用下降


def test_near_duplicate_sources_clustered():
    """同一文献的轻微改写版本应被 SimHash 聚类合并为一条来源。"""
    base = (
        "深度学习技术在图像识别领域取得了突破性进展，卷积神经网络能够有效提取图像的局部特征，"
        "并在多个基准数据集上刷新了记录，同时该方法在推理阶段保持了较低的计算开销。"
    )
    variant = (
        "深度学习技术在图像识别领域取得了突破性进展，卷积神经网络能够有效提取图像的局部特征，"
        "并在多个基准数据集上刷新了纪录，而且该方法在推理阶段维持了较低的计算开销。"
    )
    import os
    for t, c in [("聚类原文", base), ("聚类改写版", variant)]:
        if not db.doc_title_exists(t):
            did = db.add_doc(t, c, len(c))
            CORPUS.add_and_index(did)   # 模拟真实入库路径：文档进指纹库
    CORPUS.rebuild()
    r = plagiarism.run(base, {"strip_references": False})
    titles = [s["title"] for s in r["sources"]]
    assert "聚类原文" in titles
    # 两个近重复版本合并为一条来源，变体入 variants
    main = next(s for s in r["sources"] if s["title"] in ("聚类原文", "聚类改写版"))
    assert len(main["variants"]) >= 1
