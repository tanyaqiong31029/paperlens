"""索引快照持久化测试：加载/重建/哈希失效/增量脏位。"""

import pickle

import pytest

from app import db
from app.services.corpus import SNAPSHOT_VERSION, Corpus

DOCS_A = [
    (
        "图像识别研究A",
        "深度学习技术在图像识别领域取得了突破性进展。卷积神经网络能够有效提取图像的局部特征和全局语义信息。",
    ),
    ("农村电商观察B", "乡村振兴战略下农村电商发展迅速。物流体系的完善为农产品上行提供了坚实支撑。"),
]
UNIQUE = (
    "量子退相干机制涉及开放量子系统的动力学演化，本文提出新的主方程近似方法并完成数值验证实验。"
)


def _seed(docs):
    """标题去重插入（DB 为 session 共享，重复运行测试不产生重复行）。"""
    ids = []
    for title, content in docs:
        if not db.doc_title_exists(title):
            ids.append(db.add_doc(title, content, len(content)))
    return ids


@pytest.fixture()
def fresh_corpus(tmp_path):
    """每个用例独立的快照路径（构造参数注入，不依赖全局状态）。"""
    db.init_db()
    return Corpus(snapshot_path=str(tmp_path / "index.snapshot.pkl"))


def test_rebuild_then_snapshot_load(fresh_corpus):
    _seed(DOCS_A)
    assert fresh_corpus.load_or_rebuild() == "rebuilt"
    n_docs = fresh_corpus.stats()["documents"]

    with open(fresh_corpus._snap, "rb") as f:
        payload = pickle.load(f)
    assert payload["v"] == SNAPSHOT_VERSION

    # 新实例加载快照：文档数一致、检索功能可用
    fresh2 = Corpus(snapshot_path=fresh_corpus._snap)
    assert fresh2.load_or_rebuild() == "loaded"
    assert fresh2.stats()["documents"] == n_docs
    from app.services import segmenter

    probe = segmenter.split_sentences("卷积神经网络能够有效提取图像的局部特征和全局语义信息。")[0]
    hits = fresh2.find_similar(probe, 0.30)
    # 共享 DB 中可能有多个 sim=1.0 的竞争文档，断言"目标文档在满分命中之列"
    assert hits and hits[0].sim == 1.0
    assert any(h.doc_title == "图像识别研究A" for h in hits)


def test_hash_mismatch_triggers_rebuild(fresh_corpus):
    _seed(DOCS_A)
    fresh_corpus.load_or_rebuild()
    before = fresh_corpus.stats()["documents"]
    # 语料变更后哈希失效 → 重建而非加载，且新文档入索引
    db.add_doc(f"新增文档C-{id(fresh_corpus)}", UNIQUE, len(UNIQUE))
    assert fresh_corpus.load_or_rebuild() == "rebuilt"
    assert fresh_corpus.stats()["documents"] == before + 1


def test_add_and_index_marks_dirty(fresh_corpus):
    _seed(DOCS_A)
    fresh_corpus.load_or_rebuild()
    assert fresh_corpus._dirty is False
    before = fresh_corpus.stats()["documents"]
    did = db.add_doc(f"新增文档D-{id(fresh_corpus)}", UNIQUE, len(UNIQUE))
    fresh_corpus.add_and_index(did)
    assert fresh_corpus._dirty is True
    # 脏位回写后快照与新语料一致
    fresh_corpus.save_snapshot_if_dirty()
    assert fresh_corpus._dirty is False
    fresh2 = Corpus(snapshot_path=fresh_corpus._snap)
    assert fresh2.load_or_rebuild() == "loaded"
    assert fresh2.stats()["documents"] == before + 1
