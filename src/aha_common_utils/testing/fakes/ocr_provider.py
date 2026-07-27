from __future__ import annotations

from pathlib import Path

from aha_common_utils.ports.ocr_provider import OcrPageResult, OcrProviderPort
from aha_common_utils.ports.types import JsonObject
from aha_common_utils.testing.fakes._failure import FailureMixin


class FakeOcrProvider(FailureMixin, OcrProviderPort):
    """Deterministic OCR provider fake for tests."""

    def __init__(self, results: list[OcrPageResult] | None = None, *, model: str = "fake-ocr") -> None:
        super().__init__()
        self._results = list(results or [])
        self.model = model
        self.calls: list[tuple[Path, str]] = []

    async def recognize_file(self, path: Path, *, language: str = "Chinese") -> OcrPageResult:
        self._raise_if_failed()
        self.calls.append((path, language))
        if self._results:
            return self._results.pop(0)
        text = path.stem
        return OcrPageResult(
            model=self.model,
            text=text,
            markdown=text,
            usage={"pages": 1},
            metadata={"filename": path.name},
        )

    def add_result(self, result: OcrPageResult) -> None:
        self._results.append(result)

    def reset(self) -> None:
        self._results.clear()
        self.calls.clear()
        self._next_failure = None

    async def close(self) -> None:
        return None


def make_ocr_page_result(
    *,
    model: str = "fake-ocr",
    text: str = "",
    markdown: str = "",
    usage: JsonObject | None = None,
    metadata: JsonObject | None = None,
) -> OcrPageResult:
    """Build a minimal OCR page result for tests."""
    return OcrPageResult(
        model=model,
        text=text,
        markdown=markdown or text,
        usage=dict(usage or {}),
        metadata=dict(metadata or {}),
    )
