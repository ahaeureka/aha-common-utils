"""AC-1(M1): aha_common_utils.pdf.types 公共契约。

契约规则（pdf-foundation.md §6）：只有 Literal / JsonObject / bytes，
无任何领域类型——任何项目可无痛消费。
"""
import dataclasses

import pytest
from aha_common_utils.pdf.types import (
    FrontMatterDecision,
    FrontMatterPolicy,
    PdfAsset,
    PdfBlock,
    PdfDocument,
    PdfPage,
    PdfSection,
    PdfStructuralSignal,
)


def test_pdf_block_defaults_frozen():
    b = PdfBlock(kind="paragraph", text="hello", page_number=1)
    assert b.level is None
    assert b.bbox == []
    assert b.source == "text"
    assert b.metadata == {}
    # frozen + slots
    with pytest.raises(AttributeError):
        b.text = "changed"


def test_pdf_block_non_default_fields():
    b = PdfBlock(
        kind="heading",
        text="第一章 绪论",
        page_number=3,
        level=1,
        bbox=[10.0, 20.0],
        source="ocr",
        metadata={"front_matter": False},
    )
    assert b.level == 1
    assert b.source == "ocr"
    assert b.metadata == {"front_matter": False}


def test_pdf_page_defaults():
    p = PdfPage(page_number=2, text="body", blocks=[])
    assert p.page_label is None
    assert p.metadata == {}


def test_pdf_section_default_zone_is_body():
    s = PdfSection(section_id="s1", title="第一章", page_start=1, page_end=5)
    assert s.zone == "body"
    assert s.blocks == []
    assert s.assets == []


def test_pdf_asset_valid_fields():
    a = PdfAsset(kind="table_csv", data=b"a,b\n1,2", ext="csv", origin="page3")
    assert a.kind == "table_csv"
    assert a.ext == "csv"


def test_pdf_document_defaults():
    d = PdfDocument(pages=[], sections=[])
    assert d.outline is None
    assert d.page_labels == []
    assert d.metadata == {}


def test_pdf_structural_signal_defaults():
    s = PdfStructuralSignal()
    assert s.first_chapter_page is None
    assert s.page_labels == []
    assert s.outline == []  # 信号总是存在、内容可空（无 outline 即空）

def test_front_matter_decision_semantics():
    d = FrontMatterDecision(boundary_page=None, confidence=0.0, signals=[])
    assert d.boundary_page is None  # None = 判定为无 front matter（whole 正文）


def test_front_matter_policy_defaults():
    p = FrontMatterPolicy()
    assert p.strategy == "auto"
    assert p.zone_action == "separate"


def test_zone_literals():
    for z in ("front_matter", "body", "back_matter"):
        assert z in ("front_matter", "body", "back_matter")


def test_all_contract_types_are_frozen_slots():
    for cls in (PdfBlock, PdfPage, PdfSection, PdfAsset, PdfDocument,
                PdfStructuralSignal, FrontMatterDecision):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True
        assert cls.__dataclass_params__.slots is True