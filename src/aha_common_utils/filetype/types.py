"""文件类型检测的共享数据契约（避免编排器与各层实现互相循环导入）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FileTypeDetection:
    """单次类型检测结果。

    Attributes:
        mime: 最终判定 MIME 类型（如 ``application/pdf`` / ``text/plain``）。
        label: 细分标签；仅 Magika 提供（如 ``txt`` / ``html``），其余层为空串。
        extensions: 该类型的常见扩展名（仅 Magika 提供）。
        source: 命中层级：``libmagic`` | ``magika`` | ``extension`` | ``fallback``。
        score: 置信度（0~1）；仅 Magika 提供，其余层为 None。
    """

    mime: str
    label: str
    extensions: tuple[str, ...]
    source: str
    score: float | None


class FileDetector(Protocol):
    """单级检测器协议：无法判定时返回 None（而非抛异常）。"""

    source: str

    def detect(self, data: bytes) -> FileTypeDetection | None: ...


__all__ = ["FileDetector", "FileTypeDetection"]
