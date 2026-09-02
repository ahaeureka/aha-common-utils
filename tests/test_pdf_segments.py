"""AC-3(M3): aha_common_utils.pdf.segments 区块结构化启发式。

收编 k2skills：_split_paragraphs（text_html.py）、_pdf_heading_level 与
_detect_table（books.py）、"表格段不当标题"（pdf_source.py _heading_or_none）。
行为与收编前完全一致（对拍）。
"""

from __future__ import annotations

from aha_common_utils.pdf.segments import (
    detect_table,
    heading_or_none,
    merge_hyphenated_line_breaks,
    pdf_heading_level,
    split_paragraphs,
)


def test_split_paragraphs_blank_line_separated() -> None:
    md = "第一段\n\n第二段\n\n\n第三段"
    assert split_paragraphs(md) == ["第一段", "第二段", "第三段"]


def test_split_paragraphs_strips_whitespace_only() -> None:
    md = "a\n\n   \n\nb"
    assert split_paragraphs(md) == ["a", "b"]


def test_split_paragraphs_single_paragraph() -> None:
    assert split_paragraphs("只有一段") == ["只有一段"]


def test_pdf_heading_level_markdown() -> None:
    assert pdf_heading_level("# 第一章") == 1
    assert pdf_heading_level("### 小节") == 3


def test_pdf_heading_level_short_line_without_punctuation() -> None:
    assert pdf_heading_level("第一章 绪论") == 1  # ≤40 字符、无句末标点


def test_pdf_heading_level_long_or_punctuated_not_heading() -> None:
    assert pdf_heading_level("这是一个很长的段落，长度超过四十个字符并且以句号结尾。") is None
    assert pdf_heading_level("短句。") is None  # 有句末标点


def test_pdf_heading_level_empty() -> None:
    assert pdf_heading_level("") is None


def test_detect_table_tab() -> None:
    assert detect_table("a\tb\n1\t2") is True


def test_detect_table_pipe_row() -> None:
    assert detect_table("| a | b |\n| 1 | 2 |") is True
    assert detect_table("| 表头 |") is True


def test_detect_table_plain_text() -> None:
    assert detect_table("普通段落文本，无表格特征。") is False


def test_heading_or_none_table_not_heading() -> None:
    """表格段不当标题（pdf_source.py 既有规则）。"""
    assert heading_or_none("| a | b |") is None
    assert heading_or_none("a\tb") is None


def test_heading_or_none_heading_passthrough() -> None:
    assert heading_or_none("# 第一章") == 1
    assert heading_or_none("第一章 绪论") == 1


def test_merge_hyphenated_line_breaks_merges_word_splits() -> None:
    """PDF 断字 `soft-\nware` → `software`（词中断行合并）。"""
    assert merge_hyphenated_line_breaks("soft-\nware") == "software"
    assert merge_hyphenated_line_breaks("archi-\ntecture") == "architecture"
    assert merge_hyphenated_line_breaks("man-\nage") == "manage"
    assert merge_hyphenated_line_breaks("higher-\nquality") == "higher-quality"
    # 词后空格 + 连字符 + 换行（PDF 常见变体）
    assert merge_hyphenated_line_breaks("con -\ncepts") == "concepts"
    assert merge_hyphenated_line_breaks("ap -\nplication") == "application"


def test_merge_hyphenated_line_breaks_keeps_compound() -> None:
    """真复合词（第二片段是独立词）保留连字符。"""
    assert merge_hyphenated_line_breaks("step-\nby-step") == "step-by-step"
    assert merge_hyphenated_line_breaks("non-\ntrivial") == "non-trivial"
    assert merge_hyphenated_line_breaks("more-\nover") == "more-over"


def test_merge_hyphenated_line_breaks_deterministic() -> None:
    """同一输入恒等输出（确定性契约）。"""
    text = "software engineering is a soft-\nware discipline\nstep-\nby-step"
    assert merge_hyphenated_line_breaks(text) == merge_hyphenated_line_breaks(text)


def test_split_paragraphs_merges_hyphenation() -> None:
    """split_paragraphs 默认合并断行（消费方两处自动生效）。"""
    md = "soft-\nware engineering\n\nstep-\nby-step guide"
    assert split_paragraphs(md) == ["software engineering", "step-by-step guide"]


def test_split_paragraphs_long_line_no_hang() -> None:
    """超长单行（1MB+ 表格行）线性处理不卡死（re 灾难性回溯回归防护）。"""
    import time

    row = "| " + "x" * 1_100_000 + " |"
    md = "# 超限章\n\n" + row
    t0 = time.monotonic()
    paras = split_paragraphs(md)
    elapsed = time.monotonic() - t0
    assert paras and len(paras) >= 1
    # 原实现（整段 regex sub）同输入 >100s；线性实现应 <1s
    assert elapsed < 1.0

def test_merge_hyphenated_line_breaks_chained() -> None:
    """链式断字（合并后行尾又断字）全部合并。"""
    text = "soft-\nware 工程 与 step-\nby-step 流程，con -\ncepts 说明"
    assert merge_hyphenated_line_breaks(text) == (
        "software 工程 与 step-by-step 流程，concepts 说明"
    )