"""AC-2(M2): aha_common_utils.pdf.ocr_channel 空页 OCR 编排。

复用 OcrProviderPort：纯文本页直接返回；空文本页先由 page_renderer
渲染出该页图像（单页图片），再交给 OcrProviderPort.recognize_file 识别
（端口契约：recognize_file 接收单页图片文件）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
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


def _renderer_call(path: Path, page_num: int) -> Path:
    """测试渲染器：生成 单页-<page_num>.png 的伪图片路径。"""
    return path.parent / f"page-{page_num}.png"


async def test_ocr_channel_returns_text_layer_when_no_blank(tmp_path: Path) -> None:
    fake = FakeOcrProvider()
    channel = OcrChannel(fake, page_renderer=_renderer_call)
    pages = [("a", 1), ("b", 2)]
    out = await channel.ensure_text(pages, pdf_path=tmp_path / "x.pdf")
    assert out == ["a", "b"]
    assert fake.calls == []  # 无空白页 → 不触发 OCR
    assert not list(tmp_path.glob("page-*.png"))


async def test_ocr_channel_invokes_provider_for_blank_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake (not really parsed in this unit)")
    fake = FakeOcrProvider()
    channel = OcrChannel(fake, page_renderer=_renderer_call)
    pages = [("一", 1), ("", 2), ("", 3), ("三", 4)]
    out = await channel.ensure_text(pages, pdf_path=pdf_path)
    assert out[0] == "一"
    # 渲染后的单页图片路径传给 provider（含 page_num）
    assert out[1] == "page-2"  # FakeOcrProvider 默认 text = path.stem（不含 .png 后缀）
    assert out[2] == "page-3"
    assert out[3] == "三"
    assert len(fake.calls) == 2
    assert fake.calls[0] == (tmp_path / "page-2.png", "Chinese")
    assert fake.calls[1] == (tmp_path / "page-3.png", "Chinese")
    assert not fake.calls[0][0].name.startswith("book")


async def test_ocr_channel_requires_renderer_for_blank_pages(tmp_path: Path) -> None:
    """空页 OCR 必须注入 page_renderer（与业务先例 _ocr_page 语义一致）。"""
    fake = FakeOcrProvider()
    channel = OcrChannel(fake)
    pages = [("一", 1), ("", 2)]
    with pytest.raises(ValueError, match="page_renderer"):
        await channel.ensure_text(pages, pdf_path=tmp_path / "book.pdf")
    assert fake.calls == []  # 渲染缺失 → 不发 OCR 请求


async def test_ocr_channel_disabled_with_none_provider(tmp_path: Path) -> None:
    channel = OcrChannel(None)
    pages = [("a", 1), ("", 2)]
    out = await channel.ensure_text(pages, pdf_path=tmp_path / "x.pdf")
    assert out == ["a", ""]  # 无 provider → 保留空串（fail-open）


async def test_ocr_channel_config_language_passthrough(tmp_path: Path) -> None:
    fake = FakeOcrProvider()
    channel = OcrChannel(
        fake,
        config=OcrChannelConfig(language="English"),
        page_renderer=_renderer_call,
    )
    pages = [("", 1)]
    await channel.ensure_text(pages, pdf_path=tmp_path / "p.pdf")
    assert fake.calls == [(tmp_path / "page-1.png", "English")]
