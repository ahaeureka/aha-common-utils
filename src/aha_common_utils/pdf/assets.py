"""PDF 资产渲染与提取（pdf-foundation.md §8 assets）。

收编 k2skills pdf_source.py：_render_table_to_csv / _extract_page_images /
_image_extension / 资产预算常量——行为与收编前完全一致。
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

MAX_ASSET_BYTES = 1_048_576  # 单资产 1MB（防包膨胀，与 k2skills 一致）
MAX_ASSETS_PER_SECTION = 8  # 每章资产数上限（与 k2skills 一致）
ASSET_REF_PREFIX = "[资产] "  # 章节描述中资产引用行前缀（消费端依赖）


@dataclass(frozen=True, slots=True)
class AssetBudget:
    """资产预算策略（可自定义覆盖默认常量）。"""

    max_asset_bytes: int = MAX_ASSET_BYTES
    max_assets_per_section: int = MAX_ASSETS_PER_SECTION

    def would_exceed(self, *, data: bytes, asset_count: int = 0) -> bool:
        """超限判定：单资产字节超限 或 章节资产数已达上限。"""
        if len(data) > self.max_asset_bytes:
            return True
        return asset_count >= self.max_assets_per_section


def render_table_to_csv(para: str) -> bytes | None:
    """表格段（markdown 管道行 / TSV）→ CSV 字节；不可渲染 → None。

    与 k2skills 完全一致：过滤 markdown 分隔行（单元格全为 -/: 连字符）。
    """
    lines = [ln.strip() for ln in para.splitlines() if ln.strip()]
    if not lines:
        return None
    is_tsv = all("\t" in ln for ln in lines)
    rows: list[list[str]] = []
    for ln in lines:
        if is_tsv:
            cells = [c.strip() for c in ln.split("\t")]
        else:
            inner = ln.strip().strip("|")
            cells = [c.strip() for c in inner.split("|")]
        if cells and all(re.fullmatch(r":?-+:?", c) for c in cells):
            continue
        rows.append(cells)
    if not rows:
        return None
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def image_extension(data: bytes) -> str:
    """按字节 magic 判定扩展名（不依赖 pypdf 的 name 推断）；未知 → png 兜底。"""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] in (b"GIF8",):
        return "gif"
    if data[:2] == b"BM":
        return "bmp"
    return "png"


def extract_page_images(path: str, page_num: int) -> list[tuple[str, bytes]]:
    """单页内嵌位图 → [(扩展名, 图像字节)]；无图/矢量 → 空列表，不报错。

    与 k2skills 一致：提取失败不抛错（位图提取失败不影响文本编译）。
    """
    from pypdf import PdfReader

    try:
        reader = PdfReader(path)
        if page_num < 1 or page_num > len(reader.pages):
            return []
        page = reader.pages[page_num - 1]
        return [(image_extension(im.data), im.data) for im in page.images]
    except Exception:  # noqa: BLE001 —— 位图提取失败不影响文本编译
        return []