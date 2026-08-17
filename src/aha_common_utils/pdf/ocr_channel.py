"""PDF OCR 通道（pdf-foundation.md §8 ocr_channel）。

空文本页编排：渲染该页图像 → OcrProviderPort.recognize_file →
以 OCR 文本回填。无 provider 时保留空串（fail-open，不丢页）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aha_common_utils.pdf.textlayer import PageText
from aha_common_utils.ports.ocr_provider import OcrProviderPort


@dataclass(frozen=True, slots=True)
class OcrChannelConfig:
    """OCR 通道配置。"""

    language: str = "Chinese"


def empty_pages(pages: list[PageText]) -> list[int]:
    """返回空文本的物理页码列表。"""
    return [page_num for text, page_num in pages if not text.strip()]


class OcrChannel:
    """空页 OCR 回填通道（可注入 provider，无 provider 时 fail-open）。"""

    def __init__(
        self,
        provider: OcrProviderPort | None,
        *,
        config: OcrChannelConfig | None = None,
    ) -> None:
        self._provider = provider
        self._config = config or OcrChannelConfig()

    async def ensure_text(
        self,
        pages: list[PageText],
        *,
        pdf_path: Path,
    ) -> list[str]:
        """确保每个物理页有文本：空页经 OCR 回填，其余原样。"""
        if self._provider is None:
            return [text for text, _ in pages]
        blanks = empty_pages(pages)
        out: list[str] = []
        for text, page_num in pages:
            if page_num in blanks:
                result = await self._provider.recognize_file(
                    pdf_path, language=self._config.language
                )
                out.append(result.text)
            else:
                out.append(text)
        return out