"""文档解析：txt / md / docx / pdf → 纯文本。"""

import io
import re

from docx import Document as DocxDocument
from pypdf import PdfReader

from ..config import MAX_UPLOAD_MB


class ParseError(Exception):
    pass


def parse_upload(filename: str, data: bytes) -> str:
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise ParseError(f"文件超过 {MAX_UPLOAD_MB}MB 限制")
    name = filename.lower()
    if name.endswith((".txt", ".md", ".text")):
        return _decode(data)
    if name.endswith(".docx"):
        return _parse_docx(data)
    if name.endswith(".pdf"):
        return _parse_pdf(data)
    raise ParseError("仅支持 .docx / .pdf / .txt / .md 文件")


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ParseError("无法识别文本编码")


def _parse_docx(data: bytes) -> str:
    try:
        doc = DocxDocument(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        raise ParseError(f"docx 解析失败：{e}") from e
    paras = [p.text for p in doc.paragraphs]
    return "\n".join(paras)


def _parse_pdf(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "") for page in reader.pages]
    except Exception as e:  # noqa: BLE001
        raise ParseError(f"PDF 解析失败：{e}") from e
    text = "\n".join(pages)
    if not text.strip():
        raise ParseError("PDF 中未提取到文本（可能是扫描件，暂不支持 OCR）")
    return text


def strip_references(text: str) -> str:
    """去掉文末参考文献部分（按常见标题行识别），只保留正文。"""
    pattern = re.compile(
        r"^\s*(参考文献|参\s*考\s*文\s*献|致\s*谢|References|REFERENCES|Bibliography)\s*$",
        re.MULTILINE,
    )
    match = None
    for m in pattern.finditer(text):
        match = m  # 取最后一处（致谢/参考文献一般在文末）
    if match:
        return text[: match.start()]
    return text
