"""AC-6(M6): aha_common_utils.pdf.boundary.apply_zones 分区应用。

按 boundary 打 zone：front_matter 独立 section、body 起点校验不变量。
硬约束：zone 打标不丢内容、引用坐标（section_id/page）不失效。
"""

from __future__ import annotations

from aha_common_utils.pdf.boundary import apply_zones
from aha_common_utils.pdf.types import FrontMatterDecision, PdfSection


def _mk_sections() -> list[PdfSection]:
    return [
        PdfSection(section_id="sec-1", title="封面", page_start=1, page_end=1),
        PdfSection(section_id="sec-2", title="版权页", page_start=2, page_end=2),
        PdfSection(section_id="sec-3", title="目录", page_start=3, page_end=3),
        PdfSection(section_id="sec-4", title="第一章 绪论", page_start=4, page_end=6),
        PdfSection(section_id="sec-5", title="第二章 方法", page_start=7, page_end=9),
    ]


def test_apply_zones_partitions_front_matter() -> None:
    sections = _mk_sections()
    decision = FrontMatterDecision(boundary_page=4, confidence=0.9, signals=["outline"])
    zoned = apply_zones(sections, decision)
    zones = [(s.section_id, s.zone) for s in zoned]
    assert ("sec-1", "front_matter") in zones
    assert ("sec-2", "front_matter") in zones
    assert ("sec-3", "front_matter") in zones
    assert ("sec-4", "body") in zones
    assert ("sec-5", "body") in zones


def test_apply_zones_no_content_lost() -> None:
    """zone 打标不丢内容：section 数量与 section_id 集合不变。"""
    sections = _mk_sections()
    decision = FrontMatterDecision(boundary_page=4, confidence=0.9)
    zoned = apply_zones(sections, decision)
    assert len(zoned) == len(sections)
    assert {s.section_id for s in zoned} == {s.section_id for s in sections}


def test_apply_zones_body_starts_at_boundary() -> None:
    """body 起点不变量：boundary 页开始的 section 必为 body。"""
    sections = _mk_sections()
    decision = FrontMatterDecision(boundary_page=4, confidence=0.9)
    zoned = apply_zones(sections, decision)
    first_body = min((s for s in zoned if s.zone == "body"), key=lambda s: s.page_start)
    assert first_body.page_start == 4


def test_apply_zones_none_boundary_keeps_all_body() -> None:
    """fail-open：boundary=None → 全部 body（不丢内容）。"""
    sections = _mk_sections()
    decision = FrontMatterDecision(boundary_page=None, confidence=0.0)
    zoned = apply_zones(sections, decision)
    assert all(s.zone == "body" for s in zoned)


def test_apply_zones_reference_coordinates_preserved() -> None:
    """引用坐标不失效：section_id / page_start / page_end 原样保留。"""
    sections = _mk_sections()
    decision = FrontMatterDecision(boundary_page=4, confidence=0.9)
    zoned = apply_zones(sections, decision)
    for original, after in zip(sections, zoned, strict=True):
        assert after.section_id == original.section_id
        assert after.page_start == original.page_start
        assert after.page_end == original.page_end