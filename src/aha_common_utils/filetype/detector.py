"""分层文件类型检测编排器。

分层策略（快 → 准）：

1. **libmagic**：魔数头判定。命中且为"强类型"（非文本族、非空、非未知）
   → 直接返回；
2. **Magika**：第一层判定为文本族/未知时，用内容级模型细分；
3. **兜底**：两级都无果时按扩展名猜测（``mimetypes``），仍失败则
   ``application/octet-stream``。
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from aha_common_utils.filetype._magic import LibmagicDetector
from aha_common_utils.filetype._magika import MagikaDetector
from aha_common_utils.filetype.types import FileDetector, FileTypeDetection
from aha_common_utils.logging import get_logger

logger = get_logger(__name__)

#: 视为"文本族/不确定"、需要降级到 Magika 的 libmagic 判定集合。
_TEXT_LIKE_MIME_PREFIXES = ("text/",)
_TEXT_LIKE_MIME_EXACT = frozenset(
    {
        "application/json",
        "application/xml",
        "application/javascript",
        "application/x-sh",
        "application/sql",
        "application/yaml",
        "application/toml",
        "image/svg+xml",
        "application/octet-stream",  # libmagic 无法确定
    }
)
_EMPTY_MIMES = frozenset({"application/x-empty", "inode/x-empty"})
_UNKNOWN_MIME = "application/octet-stream"
_DEFAULT_READ_LIMIT = 4 * 1024 * 1024  # 检测最多读取前 4MB（Magika 足够，避免大文件全量读入）


def _needs_content_layer(mime: str) -> bool:
    """libmagic 结果是否属于文本族或不确定，需要 Magika 复核。"""
    return (
        mime.startswith(_TEXT_LIKE_MIME_PREFIXES)
        or mime in _TEXT_LIKE_MIME_EXACT
        or mime == _UNKNOWN_MIME
    )


class LayeredFileTypeDetector:
    """按 ``libmagic → Magika → 扩展名`` 顺序逐层判定的组合检测器。

    两级均可注入替换（测试可传假检测器）；缺省构造生产默认两级。
    """

    def __init__(
        self,
        primary: FileDetector | None = None,
        secondary: FileDetector | None = None,
    ) -> None:
        self._primary = primary if primary is not None else LibmagicDetector()
        self._secondary = secondary if secondary is not None else MagikaDetector()

    def detect_bytes(self, data: bytes) -> FileTypeDetection:
        """对字节缓冲执行分层判定。"""
        first = self._primary.detect(data)

        if first is not None and first.mime in _EMPTY_MIMES:
            # 空内容直接定论，不进入模型层。
            return FileTypeDetection(
                mime="application/x-empty",
                label="empty",
                extensions=(),
                source=first.source,
                score=None,
            )

        if first is not None and not _needs_content_layer(first.mime):
            return first  # 魔数头强命中（PDF/PNG/MP4/ZIP…）

        second = self._secondary.detect(data)
        if second is not None:
            return second

        if first is not None:
            return first  # 文本族但 Magika 缺席：退回 libmagic 的 text/* 判定
        return FileTypeDetection(
            mime=_UNKNOWN_MIME, label="", extensions=(), source="fallback", score=None
        )

    def detect_file(self, path: str | Path, *, max_bytes: int = _DEFAULT_READ_LIMIT) -> FileTypeDetection:
        """对磁盘文件执行分层判定（只读前 ``max_bytes`` 字节）。"""
        file_path = Path(path)
        with file_path.open("rb") as fh:
            head = fh.read(max_bytes)
        detection = self.detect_bytes(head)
        if detection.source in {"extension", "fallback"}:
            guessed = mimetypes.guess_type(file_path.name)[0]
            if guessed:
                return FileTypeDetection(
                    mime=guessed,
                    label="",
                    extensions=(),
                    source="extension",
                    score=None,
                )
        return detection


_default_detector: LayeredFileTypeDetector | None = None


def get_default_detector() -> LayeredFileTypeDetector:
    """进程级默认检测器（懒构造）。"""
    global _default_detector
    if _default_detector is None:
        _default_detector = LayeredFileTypeDetector()
    return _default_detector


def reset_default_detector() -> None:
    """重置默认检测器（测试隔离用）。"""
    global _default_detector
    _default_detector = None


def detect_file_type(path: str | Path) -> FileTypeDetection:
    """便捷入口：对磁盘文件做分层类型检测。"""
    return get_default_detector().detect_file(path)


def detect_mime_type(data: bytes) -> FileTypeDetection:
    """便捷入口：对内存缓冲做分层类型检测。"""
    return get_default_detector().detect_bytes(data)



__all__ = [
    "FileDetector",
    "FileTypeDetection",
    "LayeredFileTypeDetector",
    "detect_file_type",
    "detect_mime_type",
    "get_default_detector",
    "reset_default_detector",
]
