from __future__ import annotations

from aha_common_utils.ports.file_scan import FileScanPort, ScanResult


class ChainFileScanner(FileScanPort):
    """Run scanners in order and stop on the first non-clean verdict."""

    def __init__(self, scanners: list[FileScanPort]) -> None:
        if not scanners:
            raise ValueError("ChainFileScanner requires at least one scanner layer")
        self._scanners = scanners

    async def scan(self, *, filename: str, content: bytes, content_type: str) -> ScanResult:
        last_unscannable: ScanResult | None = None
        for scanner in self._scanners:
            try:
                result = await scanner.scan(filename=filename, content=content, content_type=content_type)
            except Exception as exc:
                last_unscannable = ScanResult(
                    verdict="UNSCANNABLE",
                    scanner_name=scanner.__class__.__name__,
                    detail=str(exc),
                )
                continue
            if result.verdict != "CLEAN":
                return result
        if last_unscannable is not None:
            return last_unscannable
        return ScanResult(verdict="CLEAN", scanner_name="chain_empty")
