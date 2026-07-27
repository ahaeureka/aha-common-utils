"""Remote OCR HTTP client."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, cast

import httpx

from aha_common_utils.json_values import flatten_numeric_list
from aha_common_utils.ports.ocr_provider import OcrLayoutBlock, OcrPageResult, OcrProviderPort
from aha_common_utils.ports.types import JsonObject


class AsyncPostClient(Protocol):
    async def post(self, url: str, *, data: dict[str, object], files: dict[str, Any]) -> Any:
        """Send a multipart POST request."""


class OcrHttpResponse(Protocol):
    status_code: int
    text: str

    def json(self) -> object:
        """Return the decoded JSON response."""


class OcrServiceError(Exception):
    """Raised when remote OCR cannot produce a usable response."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


OcrVerboseResult = OcrPageResult


class RemoteOcrClient(OcrProviderPort):
    """No-auth client for an OCR `/v1/ocr` compatible endpoint."""

    def __init__(
        self,
        *,
        api_url: str,
        timeout_seconds: float = 60.0,
        response_format: str = "verbose",
        http_client: AsyncPostClient | None = None,
    ) -> None:
        if not api_url.strip():
            raise ValueError("api_url must not be empty")
        self._api_url = api_url
        self._timeout_seconds = timeout_seconds
        self._response_format = response_format
        self._http_client = http_client

    async def recognize_file(self, path: Path, *, language: str = "Chinese") -> OcrPageResult:
        data: dict[str, object] = {"response_format": self._response_format, "language": language}
        files: dict[str, Any] = {
            "file": (path.name, path.read_bytes(), "application/octet-stream"),
        }

        try:
            response = await self._post(data=data, files=files)
        except OcrServiceError:
            raise
        except Exception as exc:
            raise OcrServiceError(f"OCR request failed: {exc}", retryable=True) from exc

        status_code = int(getattr(response, "status_code", 0))
        if status_code >= 400:
            detail = getattr(response, "text", "") or "remote OCR error"
            raise OcrServiceError(f"OCR request failed with HTTP {status_code}: {detail}", retryable=True)

        payload = response.json()
        if not isinstance(payload, dict):
            raise OcrServiceError("OCR response was not a JSON object", retryable=True)

        ocr_json = dict(payload.get("json") or {})
        return OcrPageResult(
            model=str(payload.get("model") or ""),
            text=str(payload.get("text") or ""),
            markdown=str(payload.get("markdown") or ""),
            blocks=canonical_blocks_from_verbose_json(ocr_json),
            usage=dict(payload.get("usage") or {}),
            metadata={
                "raw_json": ocr_json,
                "width": ocr_json.get("width"),
                "height": ocr_json.get("height"),
            },
        )

    async def _post(self, *, data: dict[str, object], files: dict[str, Any]) -> OcrHttpResponse:
        if self._http_client is not None:
            return await self._http_client.post(self._api_url, data=data, files=files)

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            return cast(OcrHttpResponse, await client.post(self._api_url, data=data, files=files))


def canonical_blocks_from_verbose_json(ocr_json: JsonObject) -> list[OcrLayoutBlock]:
    """Convert PP-DocLayout-style verbose JSON blocks to canonical OCR blocks."""
    raw_blocks = ocr_json.get("parsing_res_list")
    if not isinstance(raw_blocks, list):
        return []

    blocks: list[OcrLayoutBlock] = []
    for raw_block in raw_blocks:
        if not isinstance(raw_block, dict):
            continue
        block_order = raw_block.get("block_order")
        blocks.append(
            OcrLayoutBlock(
                label=str(raw_block.get("block_label") or "unknown"),
                content=str(raw_block.get("block_content") or ""),
                block_id=str(raw_block["block_id"]) if raw_block.get("block_id") is not None else None,
                order=block_order if isinstance(block_order, int) else None,
                bbox=flatten_numeric_list(raw_block.get("block_bbox")),
                polygon_points=flatten_numeric_list(raw_block.get("block_polygon_points")),
                group_id=str(raw_block["group_id"]) if raw_block.get("group_id") is not None else None,
                metadata=dict(raw_block),
            )
        )
    return blocks


_canonical_blocks_from_verbose_json = canonical_blocks_from_verbose_json
