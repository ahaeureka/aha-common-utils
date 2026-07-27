from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from aha_common_utils.ports.types import EmbeddingVector, JsonObject, LLMMessage


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
    async def close(self) -> None:
        """Release resources."""


class EmbeddingProviderPort(ABC):
    """Embedding provider contract."""

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[EmbeddingVector]:
        """Embed a list of strings."""

    @abstractmethod
    async def close(self) -> None:
        """Release resources."""
