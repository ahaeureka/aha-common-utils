from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

ScanVerdict = Literal["CLEAN", "INFECTED", "UNSCANNABLE"]


@dataclass(frozen=True, slots=True)
class ScanResult:
    verdict: ScanVerdict
    threat_name: str | None = None
    scanner_name: str = ""
    detail: str = ""

    @property
    def provider(self) -> str:
        """Backward-compatible alias for scanner identity."""
        return self.scanner_name

    @property
    def details(self) -> str:
        """Backward-compatible alias for scan detail."""
        return self.detail


class FileScanPort(ABC):
    """Scan uploaded bytes before they reach durable storage."""

    @abstractmethod
    async def scan(self, *, filename: str, content: bytes, content_type: str) -> ScanResult:
        """Return a scanner verdict for supplied file bytes."""
