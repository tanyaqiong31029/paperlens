"""查重主流程测试：基于临时库构造语料，验证命中、来源与降噪。"""
import pytest

from app import db
from app.services import plagiarism
from app.services.corpus import CORPUS


@pytest.fixture(scope="module", autouse=True)
def seed_corpus():
    doc_a = (
        "深度学习技术在图像识别领域取得了突破性进展。"
        "卷积神经网络能够有效提取图像的局部特征和全局语义信息，在分类任务中表现优异。"
        "这一项完全无关的句子用来撑起篇幅，讲述的是别的事情，不会和查询文本产生任何重合。"
    )
    doc_b = (
        "乡村振兴战略下农村电商发展迅速。"
        "物流体系的完善为农产品上行提供了坚实支撑，带动了农民增收。"
    )
    id_a = db.add_doc("图像识别研究", doc_a, len(doc_a))
    db.add_doc("农村电商观察", doc_b, len(doc_b))
    CORPUS.rebuild()
    yield id_a


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
