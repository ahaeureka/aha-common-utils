"""AC-2(M2): aha_common_utils.pdf.ocr_channel 空页 OCR 编排。

复用 OcrProviderPort：纯文本页直接返回；空文本页裁剪该页图像
（render）转 OCR；FakeOcrProvider 默认按文件名生成文本。
"""

from __future__ import annotations

from pathlib import Path

from aha_common_utils.pdf.ocr_channel import (
    OcrChannel,
    OcrChannelConfig,
    empty_pages,
)
from aha_common_utils.testing.fakes.ocr_provider import FakeOcrProvider


def test_empty_pages_detects_blank_pages() -> None:
    pages = [("正文第一页", 1), ("", 2), ("", 3), ("正文第二页", 4)]
    assert empty_pages(pages) == [2, 3]


def test_empty_pages_no_blank() -> None:
    pages = [("a", 1), ("b", 2)]
    assert empty_pages(pages) == []


async def test_ocr_channel_returns_text_layer_when_no_blank(tmp_path: Path) -> None:
    fake = FakeOcrProvider()
    channel = OcrChannel(fake)
    pages = [("a", 1), ("b", 2)]
    out = await channel.ensure_text(pages, pdf_path=tmp_path / "x.pdf")
    assert out == ["a", "b"]
    assert fake.calls == []  # 无空白页 → 不触发 OCR


async def test_ocr_channel_invokes_provider_for_blank_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake (not really parsed in this unit)")
    fake = FakeOcrProvider()
    channel = OcrChannel(fake)
    pages = [("一", 1), ("", 2), ("三", 3)]
    out = await channel.ensure_text(pages, pdf_path=pdf_path)
    assert out[0] == "一"
    assert out[1] == "book"  # FakeOcrProvider 默认 text = path.stem
    assert out[2] == "三"
    assert len(fake.calls) == 1


async def test_ocr_channel_disabled_with_none_provider(tmp_path: Path) -> None:
    channel = OcrChannel(None)
    pages = [("a", 1), ("", 2)]
    out = await channel.ensure_text(pages, pdf_path=tmp_path / "x.pdf")
    assert out == ["a", ""]  # 无 provider → 保留空串（fail-open）


async def test_ocr_channel_config_language_passthrough(tmp_path: Path) -> None:
    fake = FakeOcrProvider()
    channel = OcrChannel(fake, config=OcrChannelConfig(language="English"))
    pages = [("", 1)]
    await channel.ensure_text(pages, pdf_path=tmp_path / "p.pdf")
    assert fake.calls == [(tmp_path / "p.pdf", "English")]