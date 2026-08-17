"""PDF 处理管线主入口（pdf-foundation.md §8 pipeline）。

PdfPipeline.parse(path) -> PdfDocument：文本层 → 空页 OCR 回填 → 章节聚合。
依赖均为可注入端口（PdfTextExtractor / OcrProviderPort / LLMProviderPort），
包内不构造任何具体 provider。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from aha_common_utils.pdf.structurer import accumulate_sections
from aha_common_utils.pdf.textlayer import PdfTextExtractor, pypdf_text_extract
from aha_common_utils.pdf.types import PdfDocument, PdfPage
from aha_common_utils.ports.llm_provider import LLMProviderPort
from aha_common_utils.ports.ocr_provider import OcrProviderPort


@dataclass(frozen=True, slots=True)
class PdfPipelineConfig:
    """管线配置（依赖经端口注入，不做默认构造）。"""

    language: str = "Chinese"
    extract_assets: bool = True
    # 依赖注入（D8）：LLM 仅经 LLMProviderPort 接入，预留 boundary 语义裁决。
    # 默认 None = fail-open（不接 LLM 也能完成确定性管线）。
    llm: LLMProviderPort | None = None
    ocr: OcrProviderPort | None = None
    page_text_extractor: PdfTextExtractor | None = None
    extra: dict[str, object] = field(default_factory=dict)


class PdfPipeline:
    """解析入口：PDF 路径 → PdfDocument（确定性地完成文本层 + 聚合）。"""

    def __init__(self, config: PdfPipelineConfig | None = None) -> None:
        self._config = config or PdfPipelineConfig()

    def parse(self, path: str | Path) -> PdfDocument:
        """解析 PDF 文件为 PdfDocument（同步核心路径：文本层 + 章节聚合）。

        空页 OCR 回填属 async 编排（OcrChannel.ensure_text），由业务 async 侧
        （k2skills PdfDocumentParser.parse 先例）在迁移时接入；同步路径保持
        确定性（空页跳过、fail-open 不丢内容）。
        """
        extractor = self._config.page_text_extractor or pypdf_text_extract
        pages = extractor(str(path))

        texts = [text for text, _ in pages]
        page_objects = [
            PdfPage(page_number=num, text=text)
            for (_, num), text in zip(pages, texts, strict=True)
        ]
        sections = accumulate_sections(list(zip(texts, [num for _, num in pages], strict=True)))
        return PdfDocument(pages=page_objects, sections=sections)