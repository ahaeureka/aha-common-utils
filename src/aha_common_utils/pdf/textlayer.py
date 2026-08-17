"""PDF 文本层提取（pdf-foundation.md §8 textlayer）。

收编 k2skills 两份 _pypdf_extract（datasource/pdf_source.py 与
content/normalizer/books.py）为单一实现 pypdf_text_extract；
PdfTextExtractor 协议可注入（与 k2skills PageTextExtractor 签名一致）。
"""

from __future__ import annotations

from collections.abc import Callable

# path -> [(text, page_num)]（页码从 1 起）
PageText = tuple[str, int]
PdfTextExtractor = Callable[[str], list[PageText]]


def pypdf_text_extract(path: str) -> list[PageText]:
    """pypdf 逐页提取文本（确定性、不触网）。

    与 k2skills 既有行为一致：空页返回空字符串而非跳过；
    页码从 1 起。
    """
    from pypdf import PdfReader

    reader = PdfReader(path)
    return [(page.extract_text() or "", i + 1) for i, page in enumerate(reader.pages)]