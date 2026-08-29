"""分句、归一化、shingle 与相似度的单元测试。"""
from app.services import segmenter


def test_detect_language():
    assert segmenter.detect_language("这是一段中文内容，用于测试。") == "zh"
    assert segmenter.detect_language("This is an English sentence for testing.") == "en"


def test_split_sentences_zh():
    text = "这是第一句话。这是第二句！短句；最后一句？"
    sents = segmenter.split_sentences(text)
    assert len(sents) == 4
    assert sents[0].text == "这是第一句话。"
    assert sents[0].kind == "zh"


def test_split_sentences_en_offsets():
    text = "First sentence here. Second one follows! A third?"
    sents = segmenter.split_sentences(text)
    assert len(sents) == 3
    # 偏移量必须能还原原句
    for s in sents:
        assert text[s.start:s.end] == s.text


def test_normalize_zh_strips_punct():
    assert segmenter.normalize("深度学习（Deep Learning），是 ML 的分支！", "zh") == "深度学习DeepLearning是ML的分支"


def test_normalize_en_keeps_word_spaces():
    norm = segmenter.normalize("The Transformer, introduced in 2017, works.", "en")
    assert norm == "the transformer introduced in 2017 works"
    assert len(norm.split()) == 6


def test_shingles_and_similarity():
    norm = "深度学习技术在图像识别领域取得了突破"
    a = segmenter.Sentence(0, 0, "x", len(norm), norm, "zh")
    sa = segmenter.shingles(a)
    assert len(sa) == len(norm) - 8 + 1
    # 相同文本相似度为 1
    assert segmenter.similarity(sa, sa) == 1.0
    # 完全不同相似度为 0
    sb = {f"完全不同的内容{i}" for i in range(10)}
    assert segmenter.similarity(sa, sb) == 0.0


def test_similarity_containment_uses_min():
    """短句不被长句稀释：短句 shingles 全部包含于长句时相似度=1。"""
    short = {f"g{i}" for i in range(4)}
    long_ = short | {f"h{i}" for i in range(20)}
    assert segmenter.similarity(short, long_) == 1.0
