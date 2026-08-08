"""AsrProviderPort — 音视频转写契约（5.10.3.3）。

媒体规范化管线（AudioNormalizer/VideoNormalizer）经该端口把音频/视频转写为
带时间码的分段文本；时间码是音视频的 locator，必须在转写中保留。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AsrSegment:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True, slots=True)
class AsrResult:
    language: str
    segments: list[AsrSegment] = field(default_factory=list)


class AsrProviderPort(ABC):
    """音视频转写端口契约。"""

    @abstractmethod
    async def transcribe(self, media_path: str, *, language: str = "zh-CN") -> AsrResult:
        """转写音频/视频为带时间码的分段文本。"""

    @abstractmethod
    async def close(self) -> None:
        """释放底层资源。"""
