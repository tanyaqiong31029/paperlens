"""文件解析与报告导出测试。"""

import io

import pytest

from app import db
from app.services import parser
from app.services.exporter import export_html


def test_strip_references():
    text = "正文内容。\n\n参考文献\n[1] 张三. 研究[J]. 2020.\n[2] 李四. 更多[J]. 2021."
    kept = parser.strip_references(text)
    assert kept.startswith("正文内容。")
    assert "参考文献" not in kept and "张三" not in kept
    assert parser.strip_references("References\n[1] A. B. 2020.") == ""
    assert parser.strip_references("没有参考文献标记的正文") == "没有参考文献标记的正文"


def test_decode_gbk():
    raw = "中文内容，使用 GBK 编码。".encode("gbk")
    assert parser._decode(raw).startswith("中文内容")


def test_parse_upload_rejects_unknown_ext():
    with pytest.raises(parser.ParseError):
        parser.parse_upload("evil.exe", b"\x00\x01")


def test_parse_docx():
    from docx import Document

    doc = Document()
    doc.add_paragraph("这是一段用于测试的段落。")
    buf = io.BytesIO()
    doc.save(buf)
    text = parser.parse_upload("test.docx", buf.getvalue())
    assert "这是一段用于测试的段落。" in text


def test_export_html_contains_report():
    check_id = "test-export-001"
    db.create_check(check_id, "导出测试文档", {})
    report = {
        "plagiarism": {
            "total_rate": 12.5,
            "dup_units": 25,
            "total_units": 200,
            "sentence_count": 10,
            "matched_sentences": 2,
            "fragments": [],
            "sources": [{"doc_id": 1, "title": "某来源", "dup_units": 25, "rate": 12.5}],
            "sent_results": [],
        },
        "aigc": None,
        "options": {},
    }
    import json

    db.update_check(
        check_id,
        language="zh",
        word_count=200,
        status="done",
        report=json.dumps(report, ensure_ascii=False),
    )
    html = export_html(check_id)
    assert html and "导出测试文档" in html and "12.5%" in html
    assert export_html("no-such-id") is None
    db.delete_check(check_id)
