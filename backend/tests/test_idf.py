"""IDF 加权相似度与 df 统计测试。"""

from app.services import segmenter


def test_blended_similarity_downweights_common_shingles():
    """纯常见套话命中：containment=1.0 但 IDF 覆盖率低 → 判定分被压低；
    含独特内容的完全命中：判定分 1.0。"""
    df = {"常见短语甲": 100, "独特表述乙": 1, "独特表述丙": 1}
    n = 100
    query = {"常见短语甲", "独特表述乙"}
    cand_common_only = {"常见短语甲"}
    cand_full = {"常见短语甲", "独特表述乙", "独特表述丙"}

    cov1 = segmenter.weighted_similarity(query, cand_common_only, df, n)
    s1 = segmenter.blended_similarity(query, cand_common_only, df, n)
    s2 = segmenter.blended_similarity(query, cand_full, df, n)

    assert cov1 < 0.2  # IDF 覆盖率低 → 直接不判重
    assert s1 <= 0.5 + 0.5 * cov1 + 1e-9  # 混合判定分被压低
    assert s2 == 1.0  # 完全命中（含独特内容）不受影响


def test_weighted_similarity_perfect_match_is_one():
    s = {"甲乙丙丁戊己庚辛", "子丑寅卯辰巳午未"}
    assert segmenter.weighted_similarity(s, s, {"甲乙丙丁戊己庚辛": 1}, 10) == 1.0


def test_weighted_similarity_disjoint_is_zero():
    a = {"甲乙丙丁戊己庚辛"}
    b = {"子丑寅卯辰巳午未"}
    assert segmenter.weighted_similarity(a, b, {}, 10) == 0.0


def test_df_counts_document_frequency():
    from app import db
    from app.services.corpus import Corpus

    shared = "共享的实验设计与数据分析方法在两个文档中同时出现。"
    docs = [
        ("文档一", shared + "文档一的独特结论部分。"),
        ("文档二", shared + "文档二的独特结论部分。"),
        ("文档三", "完全不同的第三个文档内容，与共享短语没有任何交集。"),
    ]
    ids = []
    for t, c in docs:
        if not db.doc_title_exists(t):
            ids.append(db.add_doc(t, c, len(c)))
    if not ids:
        for _t, _c in docs:  # 已存在（重复运行），取现有 id
            ids.append(db.all_docs_full() and 0)
    c = Corpus(snapshot_path="/tmp/df-test.pkl")
    c.rebuild()
    shared_key = None
    for k in c.df:
        if "共享的实验设计" in k:
            shared_key = k
            break
    assert shared_key is not None
    assert c.df[shared_key] == 2  # 出现在两个文档中
