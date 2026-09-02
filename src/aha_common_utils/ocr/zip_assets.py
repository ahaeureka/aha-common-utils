"""Safe in-memory parsing of document OCR ZIP responses."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import PurePosixPath

from aha_common_utils.ports.ocr_provider import OcrAsset, OcrDocumentResult, OcrPageResult


class OcrZipError(Exception):
    """Raised when a document OCR ZIP cannot be parsed safely."""


def _safe_member_name(name: str) -> str | None:
    """Normalize a ZIP member name; return None when unsafe (traversal)."""
    if not name:
        return None
    # 统一分隔符 + 去 ./ 前导 + 拒绝绝对路径
    norm = name.replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    if norm.startswith("/") or "../" in norm or norm == "..":
        return None
    # 拒绝空段（. 或重复 /）
    parts = [p for p in norm.split("/") if p and p != "."]
    if not parts:
        return None
    return "/".join(parts)


def parse_ocr_zip(
    content: bytes,
    *,
    max_members: int = 2000,
    max_member_size: int = 10 * 1024 * 1024,  # 10 MiB / 成员
    max_total_size: int = 512 * 1024 * 1024,  # 512 MiB 总解压
) -> OcrDocumentResult:
    """Parse an OCR ZIP into OcrDocumentResult with auditable safety limits."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise OcrZipError(f"OCR response is not a valid ZIP: {exc}") from exc

    infos = zf.infolist()
    if len(infos) > max_members:
        raise OcrZipError(f"OCR ZIP has {len(infos)} members > max {max_members}")

    document_markdown = ""
    text = ""
    manifest: dict[str, object] = {}
    usage: dict[str, object] = {}
    pages: list[OcrPageResult] = []
    assets: list[OcrAsset] = []
    total = 0
    seen_required: set[str] = set()  # 重复必需成员防护
    for info in infos:
        name = _safe_member_name(info.filename)
        if name is None:
            continue  # 跳过不安全成员（不阻断整个 ZIP）
        if info.file_size > max_member_size:
            raise OcrZipError(f"OCR ZIP member {name!r} exceeds max {max_member_size} bytes")
        total += info.file_size
        if total > max_total_size:
            raise OcrZipError(f"OCR ZIP total exceeds max {max_total_size} bytes")

        if info.is_dir():
            continue
        try:
            data = zf.read(info)
        except zipfile.BadZipFile as exc:
            raise OcrZipError(f"OCR ZIP member {name!r} failed CRC/decompression: {exc}") from exc

        if name in ("result.md", "text.txt", "result.json", "usage.json"):
            if name in seen_required:
                raise OcrZipError(f"OCR ZIP duplicate required member: {name!r}")
            seen_required.add(name)

        if name == "result.md":
            document_markdown = data.decode("utf-8", errors="replace")
        elif name == "text.txt":
            text = data.decode("utf-8", errors="replace")
        elif name == "result.json":
            manifest = _load_json(data)
        elif name == "usage.json":
            usage = _load_json(data)
        elif name.startswith("pages/"):
            pages.append(_page_result_from_member(name, data))
        else:
            assets.append(
                OcrAsset(
                    relative_path=name,
                    content=data,
                    content_type=_guess_content_type(name),
                )
            )

    return OcrDocumentResult(
        document_markdown=document_markdown,
        manifest=manifest,
        usage=usage,
        text=text,
        pages=pages,
        assets=assets,
    )


def _load_json(data: bytes) -> dict[str, object]:
    try:
        value = json.loads(data.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _page_result_from_member(name: str, data: bytes) -> OcrPageResult:
    """pages/ 下成员 → OcrPageResult（markdown 页或 JSON 页）。"""
    text_data = data.decode("utf-8", errors="replace")
    if name.endswith(".json"):
        payload = _load_json(data)
        return OcrPageResult(
            model=str(payload.get("model") or ""),
            text=str(payload.get("text") or ""),
            markdown=str(payload.get("markdown") or ""),
            metadata={"member": name},
        )
    return OcrPageResult(model="", text=text_data, markdown=text_data, metadata={"member": name})


def _guess_content_type(name: str) -> str:
    """Best-effort MIME from extension."""
    suffix = PurePosixPath(name).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".pdf": "application/pdf",
        ".json": "application/json",
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".html": "text/html",
        ".css": "text/css",
    }.get(suffix, "application/octet-stream")
