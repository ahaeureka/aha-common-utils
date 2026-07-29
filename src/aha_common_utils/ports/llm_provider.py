from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

# The canonical rich EmbeddingProviderPort lives in ``embedding_provider``;
# re-exported here for backward compatibility with existing imports.
from aha_common_utils.ports.embedding_provider import EmbeddingProviderPort  # noqa: F401
from aha_common_utils.ports.types import JsonObject, LLMMessage


class LLMProviderPort(ABC):
    """Structured LLM provider contract."""

    @abstractmethod
    async def complete_json(
        self,
        *,
        messages: list[LLMMessage],
        schema: type[Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> JsonObject:
        """Return a JSON object for supplied chat messages."""

    @abstractmethod
    async def chat(
        self,
        *,
        messages: list[LLMMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        """Return the raw assistant content string for supplied chat messages."""

    @abstractmethod
    def stream_text(
        self,
        *,
        messages: list[LLMMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Yield text chunks for supplied chat messages."""

    @abstractmethod
    def stream_events(
        self,
        *,
        messages: list[LLMMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        """Yield normalized event dictionaries for supplied chat messages."""

    @abstractmethod
    async def close(self) -> None:
        """Release resources."""
