"""PDF front matter 文本启发式（pdf-foundation.md §8 heuristics）。

L3 规则：版权页 / 落款页 / 罗马页码；语言配置化（中文/英文关键词）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ROMAN_RE = re.compile(
    r"^(?=[ivxlcdm]+$)(?:m{0,4}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3}))$", re.IGNORECASE
)

# 语言配置化关键词
_ZH_COPYRIGHT = ("版权所有", "版权信息", "本书版权")
_ZH_COLOPHON = ("责任编辑", "装帧设计", "出版发行", "印刷")
_EN_COPYRIGHT = ("copyright", "all rights reserved")
_EN_COLOPHON = ("printed in", "isbn", "publisher")


@dataclass(frozen=True, slots=True)
class HeuristicsConfig:
    """文本启发式配置（语言配置化）。"""

    language: str = "Chinese"
    # 罗马页码连续跨度 ≥ 该值才算信号（默认 2，防单页误判）
    min_roman_span: int = 2


def roman_numeral(text: str) -> bool:
    """是否为罗马数字（i/ii/iv/xii…）。"""
    return bool(_ROMAN_RE.match(text.strip()))


def roman_pages(labels: list[str]) -> int:
    """返回连续罗马前缀长度（0 = 无罗马前缀）。"""
    count = 0
    for label in labels:
        if not roman_numeral(label):
            break
        count += 1
    return count


def is_copyright_page(text: str, config: HeuristicsConfig) -> bool:
    """版权页启发式。"""
    lowered = text.lower()
    if config.language.lower() == "english":
        return any(k in lowered for k in _EN_COPYRIGHT)
    return any(k in text for k in _ZH_COPYRIGHT)


def is_colophon_page(text: str, config: HeuristicsConfig) -> bool:
    """落款页/出版信息页启发式。"""
    lowered = text.lower()
    if config.language.lower() == "english":
        return any(k in lowered for k in _EN_COLOPHON)
    return any(k in text for k in _ZH_COLOPHON)
