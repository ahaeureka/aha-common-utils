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



@dataclass(frozen=True, slots=True)
class OcrAsset:
    """One binary asset extracted from a document OCR ZIP."""

    relative_path: str  # 规范化成员名（去 ./ 前导、无 ..、无绝对路径）
    content: bytes
    content_type: str  # 按扩展名推断的 MIME


@dataclass(frozen=True, slots=True)
class OcrDocumentResult:
    """Canonical document-level OCR result parsed from a ZIP response."""

    document_markdown: str  # result.md 全文（保留标题层级）
    manifest: JsonObject = field(default_factory=dict)  # result.json
    usage: JsonObject = field(default_factory=dict)  # usage.json
    text: str = ""  # text.txt
    pages: list[OcrPageResult] = field(default_factory=list)  # pages/ 下逐页
    assets: list[OcrAsset] = field(default_factory=list)  # imgs/、document/ 下资产

class OcrProviderPort(ABC):
    """OCR provider contract used by document parsers."""

    @abstractmethod
    async def recognize_file(self, path: Path, *, language: str = "Chinese") -> OcrPageResult:
        """Recognize text and layout for one image file."""

    @abstractmethod
    async def recognize_document(self, path: Path, *, language: str = "Chinese") -> OcrDocumentResult:
        """Recognize a whole document (PDF/EPUB), returning structured ZIP result."""
