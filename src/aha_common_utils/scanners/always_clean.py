from __future__ import annotations

from aha_common_utils.ports.file_scan import FileScanPort, ScanResult


class AlwaysCleanScanner(FileScanPort):
    """No-op scanner for tests and trusted local workflows."""

    async def scan(self, *, filename: str, content: bytes, content_type: str) -> ScanResult:
        return ScanResult(verdict="CLEAN", scanner_name="always_clean")
