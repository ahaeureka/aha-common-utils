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
# 行尾连字符断行检测辅助（纯字符串，无 regex——Python re 对超长行
# 含 `[a-z]+` 后接可空段模式有灾难性回溯，1MB 表格行会卡死）

def _line_end_word_hyphen(line: str) -> tuple[str, int] | None:
    """行尾是 `[a-z]+[ \t]*-[ \t]*$` → (first, first_start_idx)，否则 None。"""
    s = line.rstrip(" \t")
    if not s.endswith("-"):
        return None
    body = s[:-1].rstrip(" \t")
    j = len(body)
    while j > 0 and "a" <= body[j - 1] <= "z":
        j -= 1
    if j == len(body):
        return None
    return body[j:], j

def _line_start_word(line: str) -> tuple[str, int] | None:
    """行首 `[ \t]*([a-z]+)` → (word, end_idx)，否则 None。"""
    k = 0
    n = len(line)
    while k < n and line[k] in " \t":
        k += 1
    j = k
    while j < n and "a" <= line[j] <= "z":
        j += 1
    if j == k:
        return None
    return line[k:j], j

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

    实现按行扫描（O(n)）：逐行检查行尾 `词-` 且下一行行首为词 →
    拼接。不用整段 regex sub（Python re 对无匹配超长文本 O(n²) 病态，
    真实 1MB 表格行会卡死 parse）。
    """
    lines = text.split("\n")
    if len(lines) < 2:
        return text
    out: list[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        # 链式断字：合并后同一行尾可能又是 `词-`（soft-\nware 工程 与 step-\nby）
        while True:
            m_end = _line_end_word_hyphen(cur)
            if m_end is None or i + 1 >= len(lines):
                break
            nxt = lines[i + 1]
            m_next = _line_start_word(nxt)
            if m_next is None:
                break
            first, first_idx = m_end
            second, second_end = m_next
            rest = nxt[second_end:]
            cur = cur[:first_idx] + first + (f"-{second}" if second in _KEEP_HYPHEN_SECOND else second) + rest
            i += 1
        out.append(cur)
        i += 1
    return "\n".join(out)


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


# 句末终止符：ASCII（`.`/`!`/`?`）与 CJK/省略号（`…`/`。`/`！`/`？`）
_ASCII_TERMINATORS = ".!?"
_CJK_TERMINATORS = "…。！？"
# 可跟在终止符后的收尾字符（引号/括号/书名号）
_TRAILING_CHARS = "\"'”’)]}」』】》〉"
_TERMINATORS = _ASCII_TERMINATORS + _CJK_TERMINATORS
# 点式缩写（e.g. / i.e. / U.S. / al.）：末点不构成句末
_DOTTED_ABBREV_RE = re.compile(r"(?:[A-Za-z]\.)+[A-Za-z]?\.$")


def _is_dotted_abbreviation(text: str, dot_index: int) -> bool:
    """``text[dot_index]`` 是否为点式缩写的末点（如 ``e.g.`` / ``U.S.``）。

    只回看当前空白分隔 token；token 形如若干「单字母 + 点」再以点收尾即判为缩写。
    """
    start = dot_index
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    token = text[start : dot_index + 1]
    return len(token) <= 8 and bool(_DOTTED_ABBREV_RE.fullmatch(token))


def _emit_collapsed_ws(text: str, start: int, out: list[str], offs: list[int]) -> None:
    """逐字符发出，把空白串折叠为单个空格（偏移记在该串首字符）。"""
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in " \t\r\f\v":
            j = i
            while j < n and text[j] in " \t\r\f\v":
                j += 1
            out.append(" ")
            offs.append(start + i)
            i = j
            continue
        out.append(ch)
        offs.append(start + i)
        i += 1


def _normalize_with_offsets(text: str) -> tuple[str, list[int]]:
    """把 PDF 页文本规范化为「逻辑行」文本 + 每个字符的原文偏移。

    视觉硬换行不是句子边界：行尾断字按 ``merge_hyphenated_line_breaks`` 的同一判据连接
    （第二片段为独立复合词时保留连字符），其余换行折叠为单个空格；空白串折叠为一个
    空格。返回的偏移表使区间可回溯到原文本，供 quote_span / locator 使用。
    """
    lines: list[tuple[str, int]] = []
    pos = 0
    for line in text.split("\n"):
        lines.append((line, pos))
        pos += len(line) + 1
    out: list[str] = []
    offs: list[int] = []
    join_next = False
    for index, (line, lstart) in enumerate(lines):
        if join_next:
            lead = 0
            while lead < len(line) and line[lead] in " \t":
                lead += 1
            line = line[lead:]
            lstart += lead
            join_next = False
        m_end = _line_end_word_hyphen(line)
        if m_end is not None and index + 1 < len(lines):
            next_line, next_start = lines[index + 1]
            m_next = _line_start_word(next_line)
            if m_next is not None:
                second, _ = m_next
                body = line[: len(line.rstrip(" \t"))]
                keep = second in _KEEP_HYPHEN_SECOND
                cut = len(body) if keep else len(body) - 1
                _emit_collapsed_ws(line[:cut], lstart, out, offs)
                # 行尾空白与换行丢弃；下一行的前导空白在 join 分支跳过
                join_next = True
                continue
        _emit_collapsed_ws(line, lstart, out, offs)
        if index + 1 < len(lines) and out and out[-1] != " ":
            out.append(" ")
            offs.append(lstart + len(line))
    return "".join(out), offs


def fold_visual_line_breaks(text: str) -> str:
    """把视觉硬换行折叠为空格（并连接行尾断字），得到单行逻辑文本。

    PDF 文本层的 ``\\n`` 是**排版换行**而非语义边界；保留它会让下游把一行当成一句话。
    段落切分（按空行）必须在折叠**之前**完成，否则段落边界一起丢失。
    """
    normalized, _ = _normalize_with_offsets(text)
    return normalized.strip()


def reconstruct_sentences(text: str) -> list[tuple[str, int, int]]:
    """把 PDF 页文本重建为句子 + 原文区间 ``(sentence, start, end)``。

    先按逻辑行规范化（断字连接、视觉换行折叠），再以句末终止符切分。两类误切已排除：

    - **小数点/缩写点**：ASCII 终止符后必须是空白或文末，故 ``3.5`` 不切；点式缩写
      （``e.g.`` / ``i.e.`` / ``U.S.``）的末点不视为句末（``_is_dotted_abbreviation``）。
      代价：``et al.`` 这类单字母点式缩写同样不切，句子会并到下一个终止符——
      并句仍产出完整语句，切错则产出碎片，故取并句。
    - **CJK 无词间空白**：``。！？…`` 之后允许直接接下一句，不要求空白。

    区间为**原文本**字符偏移，故调用方可用它直接构造 quote_span / locator。
    """
    normalized, offs = _normalize_with_offsets(text)
    if not normalized.strip() or not offs:
        return []
    out: list[tuple[str, int, int]] = []
    n = len(normalized)
    start = 0
    i = 0
    while i < n:
        ch = normalized[i]
        if ch in _TERMINATORS:
            is_ascii = ch in _ASCII_TERMINATORS
            if not (is_ascii and _is_dotted_abbreviation(normalized, i)):
                j = i + 1
                while j < n and normalized[j] in _TRAILING_CHARS:
                    j += 1
                # ASCII 终止符需空白/文末作为词边界；CJK 终止符自身即边界
                if not is_ascii or j >= n or normalized[j] == " ":
                    out.append(_sentence_slice(normalized, offs, start, j))
                    start = j
                    i = j
                    continue
        i += 1
    if start < n:
        out.append(_sentence_slice(normalized, offs, start, n))
    return [s for s in out if s[0]]


def _sentence_slice(normalized: str, offs: list[int], lo: int, hi: int) -> tuple[str, int, int]:
    """切出 [lo, hi) 并去掉首尾空白，返回 (文本, 原文起, 原文止)。"""
    text = normalized[lo:hi]
    lead = len(text) - len(text.lstrip())
    trimmed = text.strip()
    if not trimmed:
        return ("", 0, 0)
    first = lo + lead
    last = first + len(trimmed) - 1
    return (trimmed, offs[first], offs[last] + 1)
def heading_or_none(para: str) -> int | None:
    """标题启发式：表格段不当标题（避免 tab 行误判章节）。"""
    if detect_table(para):
        return None
    return pdf_heading_level(para)