"""AC-4(M4): aha_common_utils.pdf.pipeline 主入口。

PdfPipeline.parse(path) -> PdfDocument：文本层 → 空页 OCR 回填 → 章节聚合。
PdfPipelineConfig 含 llm: LLMProviderPort | None 依赖注入（不与具体 provider
耦合并保留给 boundary 层语义裁决）；page_text_extractor 可注入（测试/扩展）。
"""

from __future__ import annotations

from pathlib import Path

from aha_common_utils.pdf.pipeline import PdfPipeline, PdfPipelineConfig
from aha_common_utils.pdf.structurer import SectionAccumulator, accumulate_sections
from aha_common_utils.pdf.textlayer import PageText
from aha_common_utils.ports.llm_provider import LLMProviderPort
from aha_common_utils.testing.fakes.llm_provider import FakeLLMProvider


def _write_minimal_pdf(path: Path, text: str) -> None:
    """生成 pypdf 可读的最小单页 PDF（仅 latin-1 文本）。"""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def test_pipeline_config_defaults() -> None:
    cfg = PdfPipelineConfig()
    assert cfg.language == "Chinese"
    assert cfg.extract_assets is True
    assert cfg.llm is None  # 默认不注入（fail-open）


def test_pipeline_config_llm_injection() -> None:
    llm = FakeLLMProvider()
    cfg = PdfPipelineConfig(llm=llm)
    assert isinstance(cfg.llm, LLMProviderPort)


def test_accumulate_sections_heading_driven() -> None:
    """heading 驱动聚合：标题开启新章节，段落归入当前章节。"""
    pages: list[PageText] = [
        ("Chapter 1", 1),
        ("正文第一段。", 1),
        ("Chapter 2", 2),
        ("正文第二段。", 2),
    ]
    sections = accumulate_sections(pages)
    assert [s.title for s in sections] == ["Chapter 1", "Chapter 2"]
    assert sections[0].page_start == 1
    assert sections[0].page_end == 1
    # 首块为 heading（契约 §6：level 由 PdfBlock 携带）
    assert sections[0].blocks[0].kind == "heading"
    assert [b.text for b in sections[0].blocks[1:]] == ["正文第一段。"]
    assert sections[1].page_start == 2


def test_accumulate_sections_body_before_first_heading() -> None:
    pages = [("无标题正文段。", 1)]
    sections = accumulate_sections(pages)
    assert len(sections) == 1
    assert sections[0].title == ""
    assert [b.text for b in sections[0].blocks] == ["无标题正文段。"]  # 无 heading 块


def test_accumulate_sections_skips_empty_pages() -> None:
    """空页不计入章节（与 PdfDocumentParser 的 skipped 语义一致）。"""
    pages = [("", 1), ("Chapter 1", 2), ("正文段。", 2)]
    sections = accumulate_sections(pages)
    assert len(sections) == 1
    assert sections[0].page_start == 2


def test_section_accumulator_freeze() -> None:
    acc = SectionAccumulator(section_id="sec-1", title="Chapter 1", page_start=3, heading_level=1)
    acc.paragraphs.append("正文段。")
    acc.page_end = 4
    sec = acc.freeze()
    assert sec.section_id == "sec-1"
    assert sec.page_start == 3
    assert sec.page_end == 4
    assert sec.blocks[0].kind == "heading"
    assert sec.blocks[0].level == 1
    assert [b.text for b in sec.blocks[1:]] == ["正文段。"]


def test_heading_level_carried_to_paragraph_blocks() -> None:
    """标题行的 heading index = section title（heading 本身不入 blocks）。"""
    pages = [("# Chapter 1", 1), ("正文段。", 1)]
    sections = accumulate_sections(pages)
    assert sections[0].title == "Chapter 1"
    assert sections[0].blocks[0].kind == "heading"
    assert sections[0].blocks[0].level == 1


def test_pipeline_parse_returns_document(tmp_path: Path) -> None:
    pdf = tmp_path / "book.pdf"
    _write_minimal_pdf(pdf, "Chapter 1 body text")
    pipeline = PdfPipeline()
    doc = pipeline.parse(str(pdf))
    assert len(doc.pages) == 1
    assert doc.pages[0].page_number == 1
    assert isinstance(doc.pages[0].text, str)
    assert doc.sections == [] or all(s.zone == "body" for s in doc.sections)


def test_pipeline_parse_with_injected_extractor() -> None:
    """page_text_extractor 注入：完整链路（文本层 → 聚合）不依赖 pypdf。"""

    def fake(path: str) -> list[PageText]:
        return [("Chapter 1\n\n正文第一段。\n\n正文第二段。", 1), ("Chapter 2", 2)]

    pipeline = PdfPipeline(PdfPipelineConfig(page_text_extractor=fake))
    doc = pipeline.parse("/nonexistent.pdf")
    assert [s.title for s in doc.sections] == ["Chapter 1", "Chapter 2"]
    assert [b.text for b in doc.sections[0].blocks[1:]] == ["正文第一段。", "正文第二段。"]
