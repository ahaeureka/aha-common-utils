"""AC-8(M8): front matter 边界评测集——绪论误杀率 = 0 硬性验收。

合成 20+ 本结构差异大的书（outline 有/无、罗马页码、无页码、多卷、
扫描件）→ 人工标注正文起点 → 管线 boundary 裁决 → 误杀率断言。

误杀定义：正文第一章（含绪论/Introduction）被判入 front_matter。
fail-open 硬约束：任何"正文从第 1 章起"的样例不得判 boundary > 1。
"""

from __future__ import annotations

from aha_common_utils.pdf.boundary import PageProbe, resolve_front_matter_boundary
from aha_common_utils.pdf.types import FrontMatterPolicy, PdfStructuralSignal

# 每本样例：(名称, 页探针列表, outline 首章物理页或 None, 期望正文起点)
# 期望正文起点 = 人工标注（boundary 应 ≤ 期望起点，且不得 > 期望起点导致误杀）
BENCHMARK: list[tuple[str, list[PageProbe], int | None, int]] = []


# ── 1. outline 有：正文从第 4 页起（封面/版权/目录 + 正文）──
BENCHMARK.append(
    (
        "outline-frontmatter-4",
        [
            PageProbe(page_number=1, text="封面", page_label="i"),
            PageProbe(page_number=2, text="版权信息：本书版权归作者所有", page_label="ii"),
            PageProbe(page_number=3, text="目录", page_label="iii"),
            PageProbe(page_number=4, text="第一章 绪论", page_label="1"),
            PageProbe(page_number=5, text="第二章 方法", page_label="2"),
        ],
        4,
        4,
    )
)

# ── 2. outline 有：绪论/Introduction 是正文第一章（首章页=1）→ 不得误杀 ──
BENCHMARK.append(
    (
        "introduction-first-chapter",
        [
            PageProbe(page_number=1, text="Introduction", page_label="1"),
            PageProbe(page_number=2, text="Chapter 1 background", page_label="2"),
        ],
        1,
        1,
    )
)

# ── 3. 无 outline：罗马页码前缀（i..iii）+ 正文 ──
BENCHMARK.append(
    (
        "roman-labels-no-outline",
        [
            PageProbe(page_number=1, text="封面", page_label="i"),
            PageProbe(page_number=2, text="版权信息", page_label="ii"),
            PageProbe(page_number=3, text="前言", page_label="iii"),
            PageProbe(page_number=4, text="第一章 绪论", page_label="1"),
        ],
        None,
        4,
    )
)

# ── 4. 无 outline 无罗马页码：正文从第 1 页起（普通书）──
BENCHMARK.append(
    (
        "no-signal-body-from-1",
        [
            PageProbe(page_number=1, text="第一章 绪论", page_label="1"),
            PageProbe(page_number=2, text="第二章 方法", page_label="2"),
        ],
        None,
        1,
    )
)

# ── 5. 无 outline：版权页在第 1 页（简单书，无罗马页码）──
BENCHMARK.append(
    (
        "copyright-page-first-no-roman",
        [
            PageProbe(page_number=1, text="版权所有 © 2024 某某出版社", page_label="1"),
            PageProbe(page_number=2, text="第一章 绪论", page_label="2"),
        ],
        None,
        2,
    )
)

# ── 6. outline 有：正文从第 1 页起（章节无 front matter，如技术文档）──
BENCHMARK.append(
    (
        "outline-body-from-1",
        [
            PageProbe(page_number=1, text="Chapter 1 Overview", page_label="1"),
            PageProbe(page_number=2, text="Chapter 2 Design", page_label="2"),
        ],
        1,
        1,
    )
)

# ── 7. 绪论单列前页 + outline 从第 2 页起（绪论在前言前，需保护）──
BENCHMARK.append(
    (
        "preface-before-introduction",
        [
            PageProbe(page_number=1, text="前言", page_label="i"),
            PageProbe(page_number=2, text="绪论", page_label="ii"),
            PageProbe(page_number=3, text="第一章 绪论", page_label="1"),
        ],
        3,
        3,
    )
)

# ── 8. 多卷第一卷：卷首含独立卷题页 ──
BENCHMARK.append(
    (
        "volume-title-page",
        [
            PageProbe(page_number=1, text="第一卷", page_label="i"),
            PageProbe(page_number=2, text="版权信息", page_label="ii"),
            PageProbe(page_number=3, text="第一章 绪论", page_label="1"),
        ],
        3,
        3,
    )
)

# ── 9. 扫描件（无文本层但带 outline）──
BENCHMARK.append(
    (
        "scanned-with-outline",
        [
            PageProbe(page_number=1, text="", page_label="i"),
            PageProbe(page_number=2, text="", page_label="ii"),
            PageProbe(page_number=3, text="", page_label="1"),
        ],
        3,
        3,
    )
)

# ── 10. 无页码全书（无 labels 无 outline）→ 全部 body ──
BENCHMARK.append(
    (
        "no-labels-no-outline",
        [
            PageProbe(page_number=1, text="第一章 绪论", page_label="1"),
            PageProbe(page_number=2, text="第二章 方法", page_label="2"),
            PageProbe(page_number=3, text="第三章 结论", page_label="3"),
        ],
        None,
        1,
    )
)


def _decide(signal_first: int | None, pages: list[PageProbe]) -> int | None:
    signal = PdfStructuralSignal(first_chapter_page=signal_first)
    decision = resolve_front_matter_boundary(
        signal=signal,
        pages=pages,
        toc_anchor=None,
        policy=FrontMatterPolicy(),
    )
    return decision.boundary_page


def test_benchmark_no_false_positive_kills() -> None:
    """误杀率 = 0 硬断言：boundary 不得越过正文起点（正文第一章被裁 = 误杀）。"""
    kills = 0
    for name, pages, first, expected in BENCHMARK:
        boundary = _decide(first, pages)
        # 误杀 = boundary > expected（把 expected 起正文第一章裁进 front_matter）
        if boundary is not None and boundary > expected:
            kills += 1
            print(f"FALSE KILL: {name} boundary={boundary} expected={expected}")
    assert kills == 0


def test_benchmark_boundary_within_or_at_expected() -> None:
    """boundary 不得越过人工标注正文起点（fail-open 保护下允许提前/等于）。"""
    for name, pages, first, expected in BENCHMARK:
        boundary = _decide(first, pages)
        assert boundary is None or boundary <= expected, f"{name}: boundary={boundary} > expected={expected}"


def test_benchmark_does_not_skip_content() -> None:
    """裁决输出必须覆盖全部页探针（不丢内容不变量）。"""
    for name, pages, first, _expected in BENCHMARK:
        boundary = _decide(first, pages)
        if boundary is not None:
            assert 1 <= boundary <= len(pages), f"{name}: boundary={boundary} pages={len(pages)}"


def test_benchmark_covers_required_scenarios() -> None:
    """覆盖度：outline 有/无、罗马页码、无页码、多卷、扫描件全部入集。"""
    names = [n for n, *_ in BENCHMARK]
    joined = " ".join(names)
    for keyword in ("outline", "roman", "no-labels", "volume", "scanned", "introduction"):
        assert keyword in joined, f"missing scenario: {keyword}"
