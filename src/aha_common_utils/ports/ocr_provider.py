from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from aha_common_utils.ports.types import JsonObject


@dataclass(frozen=True, slots=True)
class OcrLayoutBlock:
    """Canonical OCR layout block independent of provider response shape."""

    label: str
    content: str
    block_id: str | None = None
    order: int | None = None
    bbox: list[float] = field(default_factory=list)
    polygon_points: list[float] = field(default_factory=list)
    group_id: str | None = None
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OcrPageResult:
    """Canonical OCR page result consumed by document parsers."""

    model: str
    text: str
    markdown: str
    blocks: list[OcrLayoutBlock] = field(default_factory=list)
    usage: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)


class OcrProviderPort(ABC):
    """OCR provider contract used by document parsers."""

    @abstractmethod
    async def recognize_file(self, path: Path, *, language: str = "Chinese") -> OcrPageResult:
        """Recognize text and layout for one image file."""
