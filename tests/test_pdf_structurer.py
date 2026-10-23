"""AC-4(M4): SectionAccumulator 章节聚合单元测试。

heading 驱动聚合：标题行转结构化 heading 块、首个 heading 前正文收集为
无名 section、空页跳过、page_start/page_end 页码正确、freeze 产出 PdfSection。
"""

from __future__ import annotations

from aha_common_utils.pdf.structurer import SectionAccumulator, accumulate_sections


def test_accumulator_freeze() -> None:
    """freeze 保留 title/headings 与 blocks（html 转引擎级正文块）。"""
    acc = SectionAccumulator(section_id="s1", title="第一章 绪论", page_start=1, heading_level=1)
    acc.paragraphs.append("正文内容。")
    acc.page_end = 3
    section = acc.freeze()
    assert section.section_id == "s1"
    assert section.title == "第一章 绪论"
    assert section.page_start == 1
    assert section.page_end == 3
    assert section.blocks[0].kind == "heading"
    assert section.blocks[0].level == 1
    assert [b.text for b in section.blocks[1:]] == ["正文内容。"]


def test_accumulate_heading_opens_new_section() -> None:
    """heading 开启新章（标题去井号，标题行转 heading 块）。"""
    chapters = accumulate_sections(
        [
            ("# 第一章 绪论\n\n正文一。", 1),
            ("## 第一节\n\n小节内容。", 2),
        ]
    )
    assert [c.title for c in chapters] == ["第一章 绪论", "第一节"]
    assert chapters[0].page_start == 1
    assert chapters[0].blocks[0].level == 1
    assert chapters[1].page_start == 2
    assert chapters[1].blocks[0].level == 2
    assert [b.text for b in chapters[0].blocks[1:]] == ["正文一。"]
    assert [b.text for b in chapters[1].blocks[1:]] == ["小节内容。"]


def test_accumulate_before_first_heading_unnamed_section() -> None:
    """首个 heading 前的正文 → 无名 section（title=""，不丢内容）。"""
    chapters = accumulate_sections(
        [
            ("前置正文。", 1),
            ("# 第一章 绪论", 2),
        ]
    )
    assert len(chapters) == 2
    assert chapters[0].title == ""
    assert chapters[0].zone == "body"
    assert chapters[0].blocks[0].kind == "paragraph"
    assert chapters[1].title == "第一章 绪论"


def test_accumulate_skips_empty_pages() -> None:
    """空页跳过（不产生空 section）。"""
    chapters = accumulate_sections(
        [
            ("", 1),
            ("# 第一章 绪论", 2),
        ]
    )
    assert len(chapters) == 1
    assert chapters[0].page_start == 2


def test_accumulate_page_end_correct() -> None:
    """page_end = 章内最后一页（跨页段落归入本章）。"""
    chapters = accumulate_sections(
        [
            ("# 序\n\n序言一。", 1),
            ("序言二。", 2),
            ("# 第一章 绪论", 3),
        ]
    )
    assert chapters[0].page_start == 1
    assert chapters[0].page_end == 2
    assert chapters[1].page_start == 3
