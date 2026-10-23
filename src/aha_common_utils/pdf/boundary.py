"""PDF front matter 边界裁决（pdf-foundation.md §8 boundary）。

L0 权威信号（outline 首章页）lock → L1/L2 文本启发式校验 → L3 兜底；
默认 fail-open（无足够证据 → boundary=None，whole 正文不丢内容）。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from aha_common_utils.pdf.heuristics import (
    HeuristicsConfig,
    is_colophon_page,
    is_copyright_page,
    roman_pages,
)
from aha_common_utils.pdf.types import (
    FrontMatterDecision,
    FrontMatterPolicy,
    PdfSection,
    PdfStructuralSignal,
)


@dataclass(frozen=True, slots=True)
class PageProbe:
    """页码探针：boundary 裁决输入的最小页摘要。"""

    page_number: int
    text: str = ""
    page_label: str | None = None


# 权威信号（L0）高置信：outline 首章页即 boundary
_L0_CONFIDENCE = 0.9
# 罗马页码（L2）中等置信
_ROMAN_CONFIDENCE = 0.7
# 文本启发式（L1）低置信，不足以下判
_HEURISTIC_CONFIDENCE = 0.4


def _roman_boundary(pages: Sequence[PageProbe], config: HeuristicsConfig) -> int | None:
    """罗马页码区间 → boundary（罗马结束后下一页）；无信号 → None。"""
    labels = [p.page_label or "" for p in pages]
    span = roman_pages(labels)
    if span < config.min_roman_span:
        return None
    # boundary = 罗马区间结束后的第一页（物理页码）
    boundary_page = pages[span - 1].page_number + 1
    if boundary_page > len(pages):
        return None
    return boundary_page


def resolve_front_matter_boundary(
    *,
    signal: PdfStructuralSignal | None,
    pages: Sequence[PageProbe],
    toc_anchor: int | None,
    policy: FrontMatterPolicy,
) -> FrontMatterDecision:
    """L0 命中 lock → L1/L2 校验 → L3 兜底；默认 fail-open。

    裁决顺序：
    1. L0：outline 首章页（first_chapter_page）直接给出 boundary（高置信）。
       首章页 = 1 → 无 front matter（boundary=1，whole 正文）。
    2. L2：无 outline 时，PageLabels 罗马前缀给出中等置信 boundary。
    3. L3：业务侧 toc_anchor → boundary = toc_anchor + 1。
    4. L1 文本启发式（版权/落款页）单独不充分 → fail-open（None）。
    """
    if policy.strategy == "off":
        return FrontMatterDecision(boundary_page=None, confidence=0.0, signals=["off"])

    signals: list[str] = []
    # 语言配置：FrontMatterPolicy 无 metadata 字段（契约 §6），
    # 语言由调用方经 PdfPipelineConfig.language 传入的 policy 无关维度——
    # 此处固定 Chinese 为默认，英文场景由调用方显式传 HeuristicsConfig。
    config = HeuristicsConfig()

    # L0：权威信号 lock
    if signal is not None and signal.first_chapter_page is not None:
        boundary = signal.first_chapter_page
        signals.append("outline-first-chapter")
        return FrontMatterDecision(
            boundary_page=boundary,
            confidence=_L0_CONFIDENCE,
            signals=signals,
        )

    # L2：罗马页码前缀（中等置信）
    roman_boundary = _roman_boundary(pages, config)
    if roman_boundary is not None:
        signals.append("roman-page-labels")
        return FrontMatterDecision(
            boundary_page=roman_boundary,
            confidence=_ROMAN_CONFIDENCE,
            signals=signals,
        )

    # L3：业务侧 TOC anchor
    if toc_anchor is not None:
        signals.append("toc-anchor")
        boundary = toc_anchor + 1
        if boundary <= len(pages):
            return FrontMatterDecision(
                boundary_page=boundary,
                confidence=_ROMAN_CONFIDENCE,
                signals=signals,
            )

    # L1：文本启发式单独不充分 → fail-open
    for page in pages:
        if is_copyright_page(page.text, config) or is_colophon_page(page.text, config):
            signals.append("text-heuristic")
            break
    return FrontMatterDecision(
        boundary_page=None,
        confidence=0.0 if not signals else _HEURISTIC_CONFIDENCE,
        signals=signals,
    )


def apply_zones(
    sections: Sequence[PdfSection],
    decision: FrontMatterDecision,
) -> list[PdfSection]:
    """按 boundary 打 zone（front_matter/body/back_matter）。

    硬约束（AC-6）：
    - zone 打标不丢内容：section 数量与 section_id 不变
    - 引用坐标不失效：page_start/page_end 原样保留
    - fail-open：boundary=None → 全部 body
    - body 起点不变量：boundary 页开始的 section 必为 body
    """
    boundary = decision.boundary_page
    zoned: list[PdfSection] = []
    for section in sections:
        if boundary is None or section.page_start >= boundary:
            zone = "body"
        else:
            zone = "front_matter"
        zoned.append(
            PdfSection(
                section_id=section.section_id,
                title=section.title,
                page_start=section.page_start,
                page_end=section.page_end,
                zone=zone,
                blocks=section.blocks,
                assets=section.assets,
            )
        )
    return zoned
