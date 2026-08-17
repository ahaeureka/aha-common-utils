"""PDF 区块结构化启发式（pdf-foundation.md §8 segments）。

收编 k2skills：_split_paragraphs（text_html.py）、_pdf_heading_level 与
_detect_table（books.py）、"表格段不当标题"（pdf_source.py）——
行为与收编前完全一致。
"""

from __future__ import annotations

import re

_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")


def split_paragraphs(markdown: str) -> list[str]:
    """按空行分段落，去掉纯空白段。"""
    return [p.strip() for p in re.split(r"\n\s*\n", markdown) if p.strip()]


def pdf_heading_level(para: str) -> int | None:
    """标题启发式：markdown 标题级；短行（≤40 字符、无句末标点）近似章节标题。"""
    first = para.splitlines()[0] if para else ""
    m = _MD_HEADING_RE.match(first)
    if m:
        return len(m.group(1))
    if first and len(first) <= 40 and not re.search(r"[。．！？!?]$", first):
        return 1
    return None


def detect_table(para: str) -> bool:
    """表格启发式：含 tab 或为 markdown 管道行。"""
    if "\t" in para:
        return True
    return any(_TABLE_ROW_RE.match(line) for line in para.splitlines())


def heading_or_none(para: str) -> int | None:
    """标题启发式：表格段不当标题（避免 tab 行误判章节）。"""
    if detect_table(para):
        return None
    return pdf_heading_level(para)