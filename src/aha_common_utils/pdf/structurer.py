"""PDF 章节聚合（pdf-foundation.md §8 structurer）。

收编 k2skills pdf_source.py 的 _SectionAccumulator 聚合逻辑：
heading 驱动开启新章节，段落归入当前章节；输出公共 PdfSection 契约。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aha_common_utils.pdf.segments import heading_or_none, split_paragraphs
from aha_common_utils.pdf.textlayer import PageText
from aha_common_utils.pdf.types import PdfBlock, PdfSection


@dataclass(slots=True)
class SectionAccumulator:
    """解析期可变章节状态；完成时 freeze 为不可变 PdfSection。"""

    section_id: str
    title: str
    page_start: int
    heading_level: int | None
    paragraphs: list[str] = field(default_factory=list)
    page_end: int = 0
    table_present: bool = False
    block_kinds: list[str] = field(default_factory=list)

    def freeze(self) -> PdfSection:
        # 契约（pdf-foundation §6）：PdfSection 无 heading_level 字段，
        # heading 层级由 blocks 首块 PdfBlock(kind="heading", level=N) 携带。
        blocks: list[PdfBlock] = []
        if self.heading_level is not None and self.title:
            blocks.append(
                PdfBlock(
                    kind="heading",
                    text=self.title,
                    page_number=self.page_start,
                    level=self.heading_level,
                )
            )
        blocks.extend(
            PdfBlock(
                kind="paragraph",
                text=para,
                page_number=self.page_start,
                metadata=({"table": True} if self.table_present else {}),
            )
            for para in self.paragraphs
        )
        return PdfSection(
            section_id=self.section_id,
            title=self.title,
            page_start=self.page_start,
            page_end=self.page_end or self.page_start,
            blocks=blocks,
        )


def _heading_title(para: str) -> str:
    """markdown 标题去井号；其他原样。"""
    line = para.splitlines()[0].strip()
    if line.startswith("#"):
        stripped = line.lstrip("#").strip()
        return stripped or line
    return line


def accumulate_sections(pages: list[PageText]) -> list[PdfSection]:
    """逐页段落 → section 聚合（heading 驱动）。

    - 空页跳过（与 PdfDocumentParser.skipped 语义一致）
    - heading 段开启新章节（标题本身不入 blocks）
    - 首个 heading 之前的正文 → 无名 section（title=""，与 k2skills body 兜底一致）
    """
    sections: list[PdfSection] = []
    current: SectionAccumulator | None = None
    seq = 0

    def flush() -> None:
        nonlocal current
        if current is not None:
            sections.append(current.freeze())
        current = None

    for text, page_num in pages:
        if not text.strip():
            continue
        for para in split_paragraphs(text):
            level = heading_or_none(para)
            if level is not None:
                flush()
                seq += 1
                current = SectionAccumulator(
                    section_id=f"sec-{seq}",
                    title=_heading_title(para),
                    page_start=page_num,
                    heading_level=level,
                )
                continue
            if current is None:
                seq += 1
                current = SectionAccumulator(
                    section_id="body",
                    title="",
                    page_start=page_num,
                    heading_level=None,
                )
            current.paragraphs.append(para)
            current.page_end = page_num
    flush()
    return sections
