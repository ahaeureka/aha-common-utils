"""AC-5(M5): aha_common_utils.pdf.structural front matter 权威信号。

pypdf outline + PageLabels → PdfStructuralSignal：
- first_chapter_page（outline 首章物理页码，1-based）
- page_labels（[(物理页, 标签)]，罗马/阿拉伯）
- outline（[(标题, 物理页)]）

无 outline → 空信号（fail-open，不误判正文起点）。
"""

from __future__ import annotations

import io

from aha_common_utils.pdf.structural import (
    extract_structural_signal,
    first_chapter_page,
    outline_items,
    page_labels_from_reader,
)
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject


def _write_pdf_with_outline_and_labels() -> bytes:
    """3 页 PDF：outline 首章指向第 3 页；PageLabels: 1=i, 2=ii, 3=1。"""
    w = PdfWriter()
    for _ in range(3):
        w.add_blank_page(width=612, height=792)
    w.add_outline_item("第一章 绪论", 2)  # 0-based index 2 = 物理第 3 页

    labels = DictionaryObject(
        {
            NameObject("/Nums"): ArrayObject(
                [
                    NumberObject(0),
                    DictionaryObject({NameObject("/S"): NameObject("/r")}),
                    NumberObject(2),
                    DictionaryObject({NameObject("/S"): NameObject("/D")}),
                ]
            )
        }
    )
    w._root_object[NameObject("/PageLabels")] = labels

    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _write_plain_pdf() -> bytes:
    """无 outline 无 labels 的 2 页 PDF。"""
    w = PdfWriter()
    for _ in range(2):
        w.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_outline_items_extracts_title_and_page() -> None:
    r = PdfReader(io.BytesIO(_write_pdf_with_outline_and_labels()))
    items = outline_items(r)
    assert items == [("第一章 绪论", 3)]  # 1-based 物理页


def test_outline_items_empty_for_plain() -> None:
    r = PdfReader(io.BytesIO(_write_plain_pdf()))
    assert outline_items(r) == []


def test_page_labels_from_reader() -> None:
    r = PdfReader(io.BytesIO(_write_pdf_with_outline_and_labels()))
    labels = page_labels_from_reader(r)
    # [(物理页, 标签)]：pypdf 展开 1→i, 2→ii, 3→1
    assert labels[0][0] == 1
    assert labels[0][1] == "i"
    assert labels[2][0] == 3
    assert labels[2][1] == "1"


def test_page_labels_empty_for_plain() -> None:
    r = PdfReader(io.BytesIO(_write_plain_pdf()))
    assert page_labels_from_reader(r) == []


def test_first_chapter_page_from_outline() -> None:
    r = PdfReader(io.BytesIO(_write_pdf_with_outline_and_labels()))
    assert first_chapter_page(r) == 3  # outline 首章物理页


def test_first_chapter_page_none_for_plain() -> None:
    r = PdfReader(io.BytesIO(_write_plain_pdf()))
    assert first_chapter_page(r) is None


def test_extract_structural_signal_full() -> None:
    r = PdfReader(io.BytesIO(_write_pdf_with_outline_and_labels()))
    sig = extract_structural_signal(r)
    assert sig.first_chapter_page == 3
    assert sig.outline == [("第一章 绪论", 3)]
    assert len(sig.page_labels) == 3


def test_extract_structural_signal_empty_for_plain() -> None:
    r = PdfReader(io.BytesIO(_write_plain_pdf()))
    sig = extract_structural_signal(r)
    assert sig.first_chapter_page is None
    assert sig.outline == []
    assert sig.page_labels == []
