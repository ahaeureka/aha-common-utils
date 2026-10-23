"""PDF OCR 通道（pdf-foundation.md §8 ocr_channel）。

空文本页编排：page_renderer 渲染该页图像（单页图片）→ OcrProviderPort.
recognize_file 识别 → 以 OCR 文本回填。无 provider 时保留空串（fail-open，
不丢页）；有 provider 时空页必须注入 page_renderer（端口契约：
recognize_file 接收单页渲染图片文件，与业务先例 k2skills _ocr_page 一致）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from aha_common_utils.pdf.textlayer import PageText
from aha_common_utils.ports.ocr_provider import OcrProviderPort

# (pdf_path, 1-based page) -> 渲染出的单页图片路径
PageRenderer = Callable[[Path, int], Path]


@dataclass(frozen=True, slots=True)
class OcrChannelConfig:
    """OCR 通道配置。"""

    language: str = "Chinese"


def empty_pages(pages: list[PageText]) -> list[int]:
    """返回空文本的物理页码列表。"""
    return [page_num for text, page_num in pages if not text.strip()]


class OcrChannel:
    """空页 OCR 回填通道（provider + page_renderer 可注入）。

    - page_renderer=None 且无空页：纯文本层直通（不触发 OCR）。
    - 有空页时 page_renderer 为必填：先渲染该页为单页图片，
      再交给 OcrProviderPort.recognize_file（图片文件契约）。
    - provider=None：fail-open，所有页保留原文本（空页保持空串）。
    """

    def __init__(
        self,
        provider: OcrProviderPort | None,
        *,
        config: OcrChannelConfig | None = None,
        page_renderer: PageRenderer | None = None,
    ) -> None:
        self._provider = provider
        self._config = config or OcrChannelConfig()
        self._page_renderer = page_renderer

    async def ensure_text(
        self,
        pages: list[PageText],
        *,
        pdf_path: Path,
    ) -> list[str]:
        """确保每个物理页有文本：空页经 渲染→识别 回填，其余原样。"""
        if self._provider is None:
            return [text for text, _ in pages]
        blanks = empty_pages(pages)
        if blanks and self._page_renderer is None:
            raise ValueError(
                "page_renderer required for OCR channel with blank pages "
                "(page_renderer=...); see Parser page_renderer wiring."
            )
        renderer = self._page_renderer
        out: list[str] = []
        for text, page_num in pages:
            if page_num in blanks:
                assert renderer is not None  # blanks 非空时上方已校验
                image_path = renderer(pdf_path, page_num)
                result = await self._provider.recognize_file(image_path, language=self._config.language)
                out.append(result.markdown or result.text)
            else:
                out.append(text)
        return out
