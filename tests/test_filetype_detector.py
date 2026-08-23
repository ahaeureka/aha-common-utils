"""分层文件类型检测器单元测试。

覆盖：魔数头强命中（libmagic 层）、文本族降级（magika 层）、空内容、
未知内容兜底、文件入口、注入替身时的编排顺序。
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from aha_common_utils.filetype import (
    FileTypeDetection,
    LayeredFileTypeDetector,
    detect_file_type,
    detect_mime_type,
)
from aha_common_utils.filetype._magic import LibmagicDetector
from aha_common_utils.filetype._magika import MagikaDetector

_PDF_HEAD = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
_PNG_HEAD = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 16

_buf = io.BytesIO()
with zipfile.ZipFile(_buf, "w") as _zf:
    _zf.writestr("a.txt", "hello")
_ZIP_HEAD = _buf.getvalue()
_MARKDOWN = "# 标题\n\n第一步安装依赖。关键看风险偏好。\n".encode()
_HTML = b"<html><head><title>t</title></head><body><p>hello</p></body></html>"
_JSON = b'{"key": "value", "n": 42}\n'


class _ScriptedDetector:
    """可编程假检测器：按序返回预设结果，并记录调用。"""

    def __init__(self, source: str, results: list[FileTypeDetection | None]) -> None:
        self.source = source
        self._results = list(results)
        self.calls: list[bytes] = []

    def detect(self, data: bytes) -> FileTypeDetection | None:
        self.calls.append(data)
        if not self._results:
            return None
        return self._results.pop(0)


def test_libmagic_layer_hits_strong_binary() -> None:
    det = detect_mime_type(_PDF_HEAD)
    assert det.mime == "application/pdf"
    assert det.source == "libmagic"


def test_png_detected_by_magic_header() -> None:
    det = detect_mime_type(_PNG_HEAD)
    assert det.mime == "image/png"
    assert det.source == "libmagic"


def test_zip_detected_by_magic_header() -> None:
    det = detect_mime_type(_ZIP_HEAD)
    assert det.mime == "application/zip"
    assert det.source == "libmagic"


def test_plain_text_defers_to_magika() -> None:
    det = detect_mime_type(_MARKDOWN)
    assert det.mime.startswith("text/")
    # 文本族必须经第二层：source 为 magika（模型可用时）或 libmagic 降级。
    assert det.source in {"magika", "libmagic"}


def test_html_content_identified_as_html() -> None:
    det = detect_mime_type(_HTML)
    assert det.mime == "text/html"


def test_json_content_recognized() -> None:
    det = detect_mime_type(_JSON)
    assert det.mime in {"application/json", "text/plain"}


def test_empty_content_short_circuits() -> None:
    det = detect_mime_type(b"")
    assert det.mime == "application/x-empty"
    assert det.label == "empty"


def test_detect_file_matches_bytes(tmp_path: Path) -> None:
    p = tmp_path / "doc.pdf"
    p.write_bytes(_PDF_HEAD + b"\x00" * 64)
    det = detect_file_type(p)
    assert det.mime == "application/pdf"
    assert det.source == "libmagic"


def test_extension_fallback_when_all_layers_miss(tmp_path: Path) -> None:
    # 两级都无法判定（primary/secondary 均返回 None）→ 扩展名兜底。
    primary = _ScriptedDetector("libmagic", [None])
    secondary = _ScriptedDetector("magika", [None])
    detector = LayeredFileTypeDetector(primary=primary, secondary=secondary)
    p = tmp_path / "report.pdf"
    p.write_bytes(b"\x00" * 32)
    det = detector.detect_file(p)
    assert det.source == "extension"
    assert det.mime == "application/pdf"
    assert primary.calls and secondary.calls  # 两层确实都被调用过


def test_fallback_octet_stream_without_clues(tmp_path: Path) -> None:
    detector = LayeredFileTypeDetector(
        primary=_ScriptedDetector("libmagic", [None]),
        secondary=_ScriptedDetector("magika", [None]),
    )
    p = tmp_path / "blob.unknownext"
    p.write_bytes(b"\x00" * 8)
    det = detector.detect_file(p)
    assert det.source == "fallback"
    assert det.mime == "application/octet-stream"


def test_magika_result_wins_over_text_from_magic() -> None:
    # libmagic 判 text/plain → 必须降级；magika 返回更细的 html → 采用 magika 结果。
    primary = _ScriptedDetector(
        "libmagic",
        [FileTypeDetection(mime="text/plain", label="", extensions=(), source="libmagic", score=None)],
    )
    secondary = _ScriptedDetector(
        "magika",
        [FileTypeDetection(mime="text/html", label="html", extensions=("html",), source="magika", score=0.98)],
    )
    det = LayeredFileTypeDetector(primary=primary, secondary=secondary).detect_bytes(_HTML)
    assert det.source == "magika"
    assert det.mime == "text/html"
    assert det.score == pytest.approx(0.98)


def test_real_detectors_are_wired_by_default() -> None:
    d = LayeredFileTypeDetector()
    assert isinstance(d._primary, LibmagicDetector)
    assert isinstance(d._secondary, MagikaDetector)
