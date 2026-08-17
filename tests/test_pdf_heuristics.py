"""AC-6(M6): aha_common_utils.pdf.heuristics 文本启发式。

L3 规则：版权页/落款页/罗马页码；语言配置化（中文/英文关键词）。
"""

from __future__ import annotations

from aha_common_utils.pdf.heuristics import (
    HeuristicsConfig,
    is_colophon_page,
    is_copyright_page,
    roman_numeral,
    roman_pages,
)


def test_roman_numeral_detection() -> None:
    assert roman_numeral("i")
    assert roman_numeral("ii")
    assert roman_numeral("iv")
    assert roman_numeral("xii")
    assert not roman_numeral("1")
    assert not roman_numeral("12")
    assert not roman_numeral("")


def test_roman_pages_detects_span() -> None:
    assert roman_pages(["i", "ii", "iii", "1", "2"]) == 3  # 前 3 页罗马


def test_roman_pages_none() -> None:
    assert roman_pages(["1", "2", "3"]) == 0


def test_is_copyright_page_zh() -> None:
    cfg = HeuristicsConfig()
    assert is_copyright_page("版权所有 © 2024 某某出版社", cfg)
    assert is_copyright_page("版权信息：本书版权归作者所有", cfg)


def test_is_copyright_page_en() -> None:
    cfg = HeuristicsConfig(language="English")
    assert is_copyright_page("Copyright © 2024 Acme Press", cfg)


def test_is_copyright_page_plain_not_matched() -> None:
    cfg = HeuristicsConfig()
    assert not is_copyright_page("第一章 绪论", cfg)


def test_is_colophon_page_zh() -> None:
    cfg = HeuristicsConfig()
    assert is_colophon_page("责任编辑：某某\n装帧设计：某某", cfg)


def test_is_colophon_page_en() -> None:
    cfg = HeuristicsConfig(language="English")
    assert is_colophon_page("Printed in China 2024", cfg)


def test_is_colophon_page_plain_not_matched() -> None:
    cfg = HeuristicsConfig()
    assert not is_colophon_page("第二章 方法", cfg)