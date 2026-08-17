"""AC-6(M6): aha_common_utils.pdf.boundary front matter 边界裁决。

L0 权威信号（outline 首章页）lock → L1/L2 文本启发式校验 → L3 兜底；
默认 fail-open（无足够证据 → boundary=None，whole 正文不丢内容）。

4 类场景：outline 有/无、罗马页码有/无、误杀防护（绪论/Introduction
作为正文第一章不判 front matter）。
"""

from __future__ import annotations

from aha_common_utils.pdf.boundary import (
    PageProbe,
    resolve_front_matter_boundary,
)
from aha_common_utils.pdf.types import (
    FrontMatterPolicy,
    PdfStructuralSignal,
)


def test_outline_locks_boundary() -> None:
    """L0：outline 首章物理页 4 → boundary=4（高置信）。"""
    signal = PdfStructuralSignal(first_chapter_page=4, outline=[("第一章", 4)])
    pages = [
        PageProbe(page_number=1, text="封面", page_label="i"),
        PageProbe(page_number=2, text="版权信息", page_label="ii"),
        PageProbe(page_number=3, text="目录", page_label="iii"),
        PageProbe(page_number=4, text="第一章 绪论", page_label="1"),
    ]
    decision = resolve_front_matter_boundary(signal=signal, pages=pages, toc_anchor=None, policy=FrontMatterPolicy())
    assert decision.boundary_page == 4
    assert decision.confidence >= 0.7


def test_no_outline_but_roman_labels() -> None:
    """无 outline，但 PageLabels 罗马前缀（i..iii）→ L2 罗马信号裁决。"""
    signal = PdfStructuralSignal()  # 空信号
    pages = [
        PageProbe(page_number=1, text="封面", page_label="i"),
        PageProbe(page_number=2, text="版权信息", page_label="ii"),
        PageProbe(page_number=3, text="前言", page_label="iii"),
        PageProbe(page_number=4, text="第一章 绪论", page_label="1"),
    ]
    decision = resolve_front_matter_boundary(signal=signal, pages=pages, toc_anchor=None, policy=FrontMatterPolicy())
    # 罗马信号仅中等置信；boundary 指向罗马区间结束+1
    assert decision.boundary_page is not None
    assert decision.boundary_page == 4


def test_no_signal_no_roman_fail_open() -> None:
    """无 outline、无罗马页码 → fail-open：boundary=None（whole 正文）。"""
    signal = PdfStructuralSignal()
    pages = [
        PageProbe(page_number=1, text="第一章 绪论", page_label="1"),
        PageProbe(page_number=2, text="正文内容", page_label="2"),
    ]
    decision = resolve_front_matter_boundary(signal=signal, pages=pages, toc_anchor=None, policy=FrontMatterPolicy())
    assert decision.boundary_page is None
    assert decision.confidence == 0.0


def test_introduction_as_first_chapter_not_killed() -> None:
    """误杀防护：绪论/Introduction 是正文第一章时不得判为 front matter。"""
    signal = PdfStructuralSignal(first_chapter_page=1)
    pages = [
        PageProbe(page_number=1, text="Introduction", page_label="1"),
        PageProbe(page_number=2, text="Chapter 1 background", page_label="2"),
    ]
    decision = resolve_front_matter_boundary(signal=signal, pages=pages, toc_anchor=None, policy=FrontMatterPolicy())
    # outline 首章=1 → 无 front matter（boundary=1，whole 从第 1 页起）
    assert decision.boundary_page == 1
    assert decision.confidence > 0.0


def test_low_confidence_heuristic_falls_back_open() -> None:
    """仅靠模糊文本信号（无 outline/无罗马）→ 低置信 → fail-open。"""
    signal = PdfStructuralSignal()
    pages = [
        PageProbe(page_number=1, text="版权所有 2024", page_label="1"),
        PageProbe(page_number=2, text="第一章 绪论", page_label="2"),
    ]
    decision = resolve_front_matter_boundary(signal=signal, pages=pages, toc_anchor=None, policy=FrontMatterPolicy())
    assert decision.boundary_page is None


def test_toc_anchor_boosts_confidence() -> None:
    """业务侧 TOC anchor（目录页）参与裁决：boundary = toc_anchor + 1。"""
    signal = PdfStructuralSignal()
    pages = [
        PageProbe(page_number=1, text="封面", page_label="i"),
        PageProbe(page_number=2, text="目录", page_label="ii"),
        PageProbe(page_number=3, text="第一章 绪论", page_label="1"),
    ]
    decision = resolve_front_matter_boundary(signal=signal, pages=pages, toc_anchor=2, policy=FrontMatterPolicy())
    assert decision.boundary_page == 3