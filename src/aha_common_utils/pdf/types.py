"""PDF 公共处理能力——输出契约（pdf-foundation.md §6）。

契约规则：字段类型只允许 Literal / 原始类型 / JsonObject / bytes，
禁止任何领域类型；任何项目可无痛消费。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# 布局块类型：页面元素分类（layout.py 映射产出，业务无关标签）
PdfBlockKind = Literal[
    "page_header",  # 页眉
    "page_number",  # 页码
    "title",        # 标题（书题页）
    "heading",      # 章节标题
    "paragraph",    # 正文段落
    "table",        # 表格
    "figure",       # 插图
    "formula",      # 公式
    "footer",       # 页脚
]

# 内容来源通道
TextSource = Literal["text", "ocr"]

# 文档分区
PdfZone = Literal["front_matter", "body", "back_matter"]


@dataclass(frozen=True, slots=True)
class PdfAsset:
    """页面资产：表格 CSV / 图片 bytes，与业务无关。"""

    kind: str  # "table_csv" | "image" | ...
    data: bytes
    ext: str
    origin: str  # 页码或块索引，便于回查


@dataclass(frozen=True, slots=True)
class PdfBlock:
    """最小可寻址内容块（一段文本 / 一个标题 / 一个表格）。"""

    kind: PdfBlockKind
    text: str
    page_number: int
    level: int | None = None  # heading 级别（1=章，2=节…）
    bbox: list[float] = field(default_factory=list)  # [x0, y0, x1, y1]
    source: TextSource = "text"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PdfPage:
    """物理页：原始文本 + 结构化块 + 可选 page label。"""

    page_number: int
    text: str
    blocks: list[PdfBlock] = field(default_factory=list)
    page_label: str | None = None  # 印刷页码（i/ii/1/2…，pypdf page_labels）
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PdfSection:
    """heading 驱动的章节聚合（structurer.py 产出）。"""

    section_id: str
    title: str
    page_start: int
    page_end: int
    zone: PdfZone = "body"
    blocks: list[PdfBlock] = field(default_factory=list)
    assets: list[PdfAsset] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PdfStructuralSignal:
    """front matter 权威信号（structural.py 产出，pypdf outline + page labels）。"""

    first_chapter_page: int | None = None  # outline 首章页码（物理页）
    page_labels: list[tuple[int, str]] = field(default_factory=list)  # [(物理页, 标签)]
    outline: list[tuple[str, int]] = field(default_factory=list)  # [(标题, 物理页)]


@dataclass(frozen=True, slots=True)
class PdfDocument:
    """PdfPipeline.parse 的顶层输出。"""

    pages: list[PdfPage]
    sections: list[PdfSection]
    outline: list[tuple[str, int]] | None = None
    page_labels: list[tuple[int, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FrontMatterDecision:
    """front matter 边界裁决结果（boundary.py 产出）。"""

    boundary_page: int | None  # None = 无 front matter（whole 正文，fail-open）
    confidence: float
    signals: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FrontMatterPolicy:
    """front matter 分区策略（policy.py 消费）。"""

    strategy: Literal["auto", "strict", "off"] = "auto"
    zone_action: Literal["separate", "discard"] = "separate"