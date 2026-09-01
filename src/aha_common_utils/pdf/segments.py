"""PDF 区块结构化启发式（pdf-foundation.md §8 segments）。

收编 k2skills：_split_paragraphs（text_html.py）、_pdf_heading_level 与
_detect_table（books.py）、"表格段不当标题"（pdf_source.py）——
行为与收编前完全一致。
"""

from __future__ import annotations

import re

_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
# 行尾连字符断行：`soft-\nware` / `con -\ncepts`（PDF 排版断字；允许连字符前有空格）
_LINE_BREAK_HYPHEN_RE = re.compile(r"([a-z]+)[ \t]*-[ \t]*\n[ \t]*([a-z]+)")

# 第二片段为这些常见词 → 保留连字符（真实复合词，如 higher-quality/step-by-step）
_KEEP_HYPHEN_SECOND: frozenset[str] = frozenset({
    "by", "quality", "trivial", "over", "in", "depth", "time", "step",
    "based", "level", "end", "to", "of", "on", "off", "up", "down",
    "line", "free", "proof", "aware", "driven", "grade", "tier", "hand",
    "side", "third", "party", "well", "known", "built", "first",
})


def merge_hyphenated_line_breaks(text: str) -> str:
    """合并 PDF 行尾连字符断行（`soft-\nware` → `software`）。

    仅当第二片段是独立英文复合词（如 `quality`/`by`）时保留连字符，
    避免把 `higher-quality`/`step-by-step` 误合并。确定性、无外部词典。
    """
    def _rep(m: re.Match[str]) -> str:
        first, second = m.group(1), m.group(2)
        if second in _KEEP_HYPHEN_SECOND:
            return f"{first}-{second}"
        return first + second

    return _LINE_BREAK_HYPHEN_RE.sub(_rep, text)


def split_paragraphs(markdown: str) -> list[str]:
    """按空行分段落，去掉纯空白段；合并行尾连字符断行。"""
    merged = merge_hyphenated_line_breaks(markdown)
    return [p.strip() for p in re.split(r"\n\s*\n", merged) if p.strip()]



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