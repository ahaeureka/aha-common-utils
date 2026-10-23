"""AC-1(M1): aha_common_utils.pdf.textlayer 文本层提取。

收编 k2skills 两份 _pypdf_extract 为单一实现 pypdf_text_extract；
PdfTextExtractor 协议可注入（与 PdfBookNormalizer 的 PageTextExtractor
签名一致：path -> [(text, page_num)]）。
"""

from __future__ import annotations

from pathlib import Path

from aha_common_utils.pdf.textlayer import (
    PageText,
    PdfTextExtractor,
    pypdf_text_extract,
)


def _write_minimal_pdf(path: Path, text: str) -> None:
    """生成 pypdf 可读的最小单页 PDF（含一条 Helvetica 文本流）。"""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def test_pypdf_text_extract_single_page(tmp_path: Path) -> None:
    pdf = tmp_path / "one.pdf"
    _write_minimal_pdf(pdf, "Hello World")
    pages = pypdf_text_extract(str(pdf))
    assert pages == [("Hello World", 1)]


def test_pypdf_text_extract_empty_page_returns_empty_string(tmp_path: Path) -> None:
    pdf = tmp_path / "empty.pdf"
    _write_minimal_pdf(pdf, "")
    pages = pypdf_text_extract(str(pdf))
    assert pages == [("", 1)]


def test_injectable_extractor_signature() -> None:
    """PdfTextExtractor 可注入（对拍 k2skills PageTextExtractor 场景）。"""

    def fake(path: str) -> list[PageText]:
        return [("页1", 1), ("页2", 2)]

    extractor: PdfTextExtractor = fake
    assert extractor("/nonexistent.pdf") == [("页1", 1), ("页2", 2)]


def test_pypdf_text_extract_returns_one_entry_per_page(tmp_path: Path) -> None:
    """单页 PDF → 恰好 [(text, 1)]（页码从 1 起，与 k2skills 行为一致）。"""
    pdf = tmp_path / "multi_attempt.pdf"
    _write_minimal_pdf(pdf, "x")
    pages = pypdf_text_extract(str(pdf))
    assert len(pages) == 1
    assert pages[0][1] == 1
