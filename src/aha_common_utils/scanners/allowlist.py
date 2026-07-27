from __future__ import annotations

from aha_common_utils.ports.file_scan import FileScanPort, ScanResult


class MimeTypeAllowlistScanner(FileScanPort):
    """Reject files whose MIME type is not explicitly allowed."""

    def __init__(self, allowed_types: list[str] | tuple[str, ...] | set[str]) -> None:
        self._allowed_types = frozenset(allowed_types)

    async def scan(self, *, filename: str, content: bytes, content_type: str) -> ScanResult:
        if content_type in self._allowed_types:
            return ScanResult(verdict="CLEAN", scanner_name="mime_allowlist")
        return ScanResult(
            verdict="INFECTED",
            threat_name=f"MIME type blocked: {content_type}",
            scanner_name="mime_allowlist",
            detail=f"Allowed types: {', '.join(sorted(self._allowed_types))}",
        )
