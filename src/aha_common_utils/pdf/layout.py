"""PDF 版面标签映射（pdf-foundation.md §8 layout）。

将 OCR 通道 OcrLayoutBlock.label 映射为公共 PdfBlockKind；
Front matter 专有标签（copyright/toc/colophon/dedication）归入 paragraph，
不新增 kind（zone 由 boundary 层裁决）。
"""

from __future__ import annotations

import re

from aha_common_utils.pdf.types import PdfBlockKind
from aha_common_utils.ports.ocr_provider import OcrLayoutBlock

_HEADING_LEVEL_RE = re.compile(r"^heading(?:_([1-6]))?$")

# OCR label → 公共 kind（未列出的回退 paragraph）
_LABEL_TO_KIND: dict[str, PdfBlockKind] = {
    "title": "title",
    "text": "paragraph",
    "body": "paragraph",
    "table": "table",
    "figure": "figure",
    "image": "figure",
    "formula": "formula",
    "header": "page_header",
    "footer": "footer",
    "page_number": "page_number",
    "page_num": "page_number",
    "heading": "heading",
    "section_heading": "heading",
    "subheading": "heading",
    # front matter 专有标签：归入 paragraph（zone 由 boundary 裁决）
    "copyright": "paragraph",
    "toc": "paragraph",
    "colophon": "paragraph",
    "dedication": "paragraph",
    "epigraph": "paragraph",
    "part": "heading",
}


def block_kind_for_ocr_label(
    label: str,
    *,
    with_level: bool = False,
) -> PdfBlockKind | tuple[PdfBlockKind, int | None]:
    """映射单个 OCR 标签 → PdfBlockKind。

    with_level=True 时返回 (kind, level)，heading_N → level=N；
    普通 heading → level=None。
    """
    m = _HEADING_LEVEL_RE.match(label)
    if m:
        kind: PdfBlockKind = "heading"
        level: int | None = int(m.group(1)) if m.group(1) else None
        return (kind, level) if with_level else kind
    kind = _LABEL_TO_KIND.get(label, "paragraph")
    return (kind, None) if with_level else kind


def classify_ocr_blocks(blocks: list[OcrLayoutBlock]) -> list[PdfBlockKind]:
    """整页 OCR 块 → kind 序列（按 order 排序）。"""
    ordered = sorted(blocks, key=lambda b: b.order if b.order is not None else 0)
    return [block_kind_for_ocr_label(b.label) for b in ordered]  # type: ignore[return-value]