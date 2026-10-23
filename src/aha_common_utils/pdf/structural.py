"""PDF front matter 权威信号（pdf-foundation.md §8 structural）。

pypdf outline + PageLabels → PdfStructuralSignal：
- first_chapter_page：outline 首章物理页码（1-based）
- page_labels：[(物理页, 标签)]（罗马/阿拉伯，仅当 PDF 显式声明 /PageLabels）
- outline：[(标题, 物理页)]

无 outline → 空信号（fail-open：boundary 层退化为文本启发式，
不误判正文起点）。
"""

from __future__ import annotations

from typing import Any, cast

from pypdf import PdfReader

from aha_common_utils.pdf.types import PdfStructuralSignal


def outline_items(reader: PdfReader) -> list[tuple[str, int]]:
    """outline → [(标题, 1-based 物理页)]；无 outline → 空列表。

    pypdf outline 项为 Destination（dict 子类）：'/Title' 标题，
    '/Page' 为页面 indirect reference；物理页码通过页面
    indirect_reference 匹配 pages 列表定位（1-based）。
    """
    items: list[tuple[str, int]] = []
    pages = list(reader.pages)
    for item in reader.outline:
        d = cast(dict[str, Any], item)
        title = d.get("/Title")
        page_ref = d.get("/Page")
        if title is None or page_ref is None:
            continue
        for index, page in enumerate(pages):
            if page.indirect_reference == page_ref:
                items.append((str(title), index + 1))
                break
    return items


def page_labels_from_reader(reader: PdfReader) -> list[tuple[int, str]]:
    """显式 PageLabels → [(1-based 物理页, 标签)]；无显式声明 → 空列表。

    仅当 /Root 声明 /PageLabels 才产出（pypdf 对无声明 PDF 默认
    展开为阿拉伯标签，会误报；此处按设计只认显式声明）。
    pypdf 6.x reader.page_labels 为按页序展开的 list[str]。
    """
    root = cast(dict[str, Any], reader.root_object)
    if "/PageLabels" not in root:
        return []
    raw = getattr(reader, "page_labels", None)
    if not raw:
        return []
    return [(index + 1, str(label)) for index, label in enumerate(raw)]


def first_chapter_page(reader: PdfReader) -> int | None:
    """outline 首章物理页码（1-based）；无 outline → None。"""
    items = outline_items(reader)
    if not items:
        return None
    return items[0][1]


def extract_structural_signal(reader: PdfReader) -> PdfStructuralSignal:
    """从已打开的 PdfReader 提取权威信号（空信号 = fail-open）。"""
    items = outline_items(reader)
    return PdfStructuralSignal(
        first_chapter_page=items[0][1] if items else None,
        page_labels=page_labels_from_reader(reader),
        outline=items,
    )
