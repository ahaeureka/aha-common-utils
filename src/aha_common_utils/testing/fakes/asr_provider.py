from __future__ import annotations

from aha_common_utils.ports.asr_provider import AsrProviderPort, AsrResult, AsrSegment


class FakeAsrProvider(AsrProviderPort):
    """Deterministic ASR provider fake for tests."""

    def __init__(
        self,
        segments: list[AsrSegment] | None = None,
        *,
        language: str = "zh-CN",
    ) -> None:
        self._segments = list(segments) if segments else [AsrSegment(0, 1000, "转写文本")]
        self._language = language
        self.calls: list[tuple[str, str]] = []

    async def transcribe(self, media_path: str, *, language: str = "zh-CN") -> AsrResult:
        self.calls.append((media_path, language))
        return AsrResult(language=language, segments=list(self._segments))

    async def close(self) -> None:
        return None

    def reset(self) -> None:
        self.calls.clear()
