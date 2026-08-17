"""AC-2(M2): aha_common_utils.pdf.layout 版面标签 → PdfBlockKind 映射。

OCR 通道的 OcrLayoutBlock.label（"title"/"text"/"table"/"figure"…）
映射为公共 PdfBlockKind 标签；front matter 专有标签（"copyright"/"toc"）
经扩展标签解析归入对应 kind。
"""

from __future__ import annotations

from aha_common_utils.pdf.layout import (
    block_kind_for_ocr_label,
    classify_ocr_blocks,
)
from aha_common_utils.ports.ocr_provider import OcrLayoutBlock


def test_block_kind_for_ocr_label_known() -> None:
    assert block_kind_for_ocr_label("title") == "title"
    assert block_kind_for_ocr_label("text") == "paragraph"
    assert block_kind_for_ocr_label("table") == "table"
    assert block_kind_for_ocr_label("figure") == "figure"
    assert block_kind_for_ocr_label("formula") == "formula"


def test_block_kind_for_ocr_label_header_footer() -> None:
    assert block_kind_for_ocr_label("header") == "page_header"
    assert block_kind_for_ocr_label("footer") == "footer"
    assert block_kind_for_ocr_label("page_number") == "page_number"


def test_block_kind_for_ocr_label_heading() -> None:
    assert block_kind_for_ocr_label("heading") == "heading"
    assert block_kind_for_ocr_label("section_heading") == "heading"


def test_block_kind_for_ocr_label_unknown_falls_back_paragraph() -> None:
    assert block_kind_for_ocr_label("unknown_label") == "paragraph"


def test_block_kind_for_ocr_label_heading_level_extracted() -> None:
    kind, level = block_kind_for_ocr_label("heading", with_level=True)
    assert kind == "heading"
    assert level is None


def test_classify_ocr_blocks_maps_sequence() -> None:
    blocks = [
        OcrLayoutBlock(label="title", content="The Book", order=0),
        OcrLayoutBlock(label="text", content="正文段落", order=1),
        OcrLayoutBlock(label="table", content="a\tb", order=2),
        OcrLayoutBlock(label="figure", content="", order=3),
        OcrLayoutBlock(label="unknown", content="x", order=4),
    ]
    kinds = classify_ocr_blocks(blocks)
    assert kinds == ["title", "paragraph", "table", "figure", "paragraph"]


def test_front_matter_labels_map_to_paragraph_blocks() -> None:
    """front matter 专有标签（版权页/目录）归入 paragraph（不新增 kind）。"""
    for label in ("copyright", "toc", "colophon", "dedication"):
        assert block_kind_for_ocr_label(label) == "paragraph"


def test_heading_level_from_numbered_label() -> None:
    kind, level = block_kind_for_ocr_label("heading_1", with_level=True)
    assert kind == "heading"
    assert level == 1
    kind2, level2 = block_kind_for_ocr_label("heading_3", with_level=True)
    assert (kind2, level2) == ("heading", 3)