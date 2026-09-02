"""Slice 9 聚焦测试：recognize_document + 安全 ZIP 解析。"""

from __future__ import annotations

import io
import json
import struct
import zipfile
from pathlib import Path
from typing import Any

import pytest
from aha_common_utils.adapters.remote_ocr import OcrServiceError, RemoteOcrClient
from aha_common_utils.ocr.zip_assets import OcrZipError, parse_ocr_zip
from aha_common_utils.ports.ocr_provider import OcrDocumentResult
from aha_common_utils.testing.fakes.ocr_provider import FakeOcrProvider


def _make_zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


class _FakeHttp:
    """AsyncPostClient 双工 mock：记录 data/files，返回可控响应。"""

    def __init__(self, *, status: int = 200, content: bytes = b"") -> None:
        self.status = status
        self._content = content
        self.calls: list[tuple[dict[str, object], dict[str, Any]]] = []

    async def post(self, url: str, *, data: dict[str, object], files: dict[str, Any]) -> Any:
        self.calls.append((data, files))

        class _Resp:
            status_code = self.status
            text = "err" if self.status >= 400 else ""
            content = self._content

            def json(self) -> object:
                return {}

        return _Resp()


async def test_recognize_document_posts_zip_format(tmp_path: Path) -> None:
    zip_bytes = _make_zip({"result.md": b"# Chapter 1\n\nBody"})
    http = _FakeHttp(content=zip_bytes)
    client = RemoteOcrClient(api_url="http://ocr", http_client=http)
    doc = tmp_path / "doc.pdf"
    doc.write_bytes(b"%PDF-1.4")
    result = await client.recognize_document(doc)
    data, files = http.calls[0]
    assert data["response_format"] == "zip"
    assert data["language"] == "Chinese"
    assert "file" in files
    assert result.document_markdown.startswith("# ")


async def test_parse_ocr_zip_extracts_all_sections() -> None:
    zip_bytes = _make_zip(
        {
            "result.json": json.dumps({"title": "T", "pages": 2}).encode(),
            "result.md": b"# Chapter 1\n\nBody",
            "text.txt": b"plain text",
            "usage.json": json.dumps({"tokens": 123}).encode(),
            "pages/p1.md": b"# Page 1\ncontent",
            "imgs/a.png": b"\x89PNG\r\n",
        }
    )
    result = parse_ocr_zip(zip_bytes)
    assert result.manifest == {"title": "T", "pages": 2}
    assert result.usage == {"tokens": 123}
    assert result.document_markdown.startswith("# Chapter 1")
    assert result.text == "plain text"
    assert len(result.pages) == 1 and result.pages[0].markdown.startswith("# Page 1")
    assert result.assets and result.assets[0].relative_path == "imgs/a.png"
    assert result.assets[0].content_type == "image/png"


def test_parse_ocr_zip_rejects_traversal() -> None:
    zip_bytes = _make_zip(
        {
            "result.md": b"# ok",
            "../evil.txt": b"evil",
        }
    )
    result = parse_ocr_zip(zip_bytes)
    assert result.document_markdown.startswith("# ok")
    assert all(a.relative_path != "../evil.txt" for a in result.assets)


def test_parse_ocr_zip_enforces_limits() -> None:
    zip_bytes = _make_zip({"a.txt": b"x", "b.txt": b"y"})
    with pytest.raises(OcrZipError):
        parse_ocr_zip(zip_bytes, max_members=1)
    big = _make_zip({"big.bin": b"x" * 100})
    with pytest.raises(OcrZipError):
        parse_ocr_zip(big, max_member_size=10)


def test_parse_ocr_zip_bad_zip_raises() -> None:
    with pytest.raises(OcrZipError):
        parse_ocr_zip(b"not a zip")


def test_parse_ocr_zip_duplicate_required_member_raises() -> None:
    # dict 不能表达重复键——直接两次 writestr 同名成员（ZIP 规范允许）
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("result.md", b"# a")
        zf.writestr("result.md", b"# b")
    with pytest.raises(OcrZipError):
        parse_ocr_zip(buf.getvalue())


def test_parse_ocr_zip_crc_error_classified() -> None:
    # 构造 CRC 损坏的 ZIP：篡改第一个成员的数据字节（本地文件头后）
    zip_bytes = _make_zip({"result.md": b"# ok"})
    raw = bytearray(zip_bytes)
    idx = raw.find(b"PK\x03\x04")
    name_len = struct.unpack("<H", raw[idx + 26 : idx + 28])[0]
    extra_len = struct.unpack("<H", raw[idx + 28 : idx + 30])[0]
    data_off = idx + 30 + name_len + extra_len
    raw[data_off] ^= 0xFF
    with pytest.raises(OcrZipError):
        parse_ocr_zip(bytes(raw))


def test_parse_ocr_zip_dir_members_skipped() -> None:
    zip_bytes = _make_zip({"imgs/": b"", "imgs/a.png": b"\x89PNG"})
    result = parse_ocr_zip(zip_bytes)
    assert [a.relative_path for a in result.assets] == ["imgs/a.png"]


async def test_fake_ocr_provider_recognize_document(tmp_path: Path) -> None:
    doc = tmp_path / "doc.pdf"
    doc.write_bytes(b"pdf")
    provider = FakeOcrProvider()
    result = await provider.recognize_document(doc)
    assert result.document_markdown == "# doc\n\ndoc"
    assert provider.document_calls == [(doc, "Chinese")]
    injected = OcrDocumentResult(document_markdown="# injected")
    provider.add_document_result(injected)
    assert (await provider.recognize_document(doc)).document_markdown == "# injected"


async def test_recognize_document_http_error_raises(tmp_path: Path) -> None:
    http = _FakeHttp(status=500)
    client = RemoteOcrClient(api_url="http://ocr", http_client=http)
    doc = tmp_path / "doc.pdf"
    doc.write_bytes(b"%PDF-1.4")
    with pytest.raises(OcrServiceError) as exc:
        await client.recognize_document(doc)
    assert exc.value.retryable is True


async def test_recognize_document_empty_body_raises(tmp_path: Path) -> None:
    http = _FakeHttp(content=b"")
    client = RemoteOcrClient(api_url="http://ocr", http_client=http)
    doc = tmp_path / "doc.pdf"
    doc.write_bytes(b"%PDF-1.4")
    with pytest.raises(OcrServiceError):
        await client.recognize_document(doc)
