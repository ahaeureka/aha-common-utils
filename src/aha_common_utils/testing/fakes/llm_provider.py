from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from aha_common_utils.ports.embedding_provider import EmbeddingProviderPort
from aha_common_utils.ports.llm_provider import LLMProviderPort
from aha_common_utils.ports.types import EmbeddingVector, JsonObject, LLMMessage
from aha_common_utils.testing.fakes._failure import FailureMixin


class FakeLLMProvider(FailureMixin, LLMProviderPort):
    def __init__(self, responses: list[JsonObject] | None = None, raw_responses: list[str] | None = None) -> None:
        super().__init__()
        self.responses: list[JsonObject] = list(responses or [{"status": "ok"}])
        self.raw_responses = list(raw_responses or [])
        self.requests: list[list[LLMMessage]] = []
        self._text_chunks: list[str] = []
        self._event_chunks: list[list[dict[str, object]]] = []
        self.stream_text_calls: list[list[LLMMessage]] = []
        self.stream_events_calls: list[list[LLMMessage]] = []

    def set_text_chunks(self, chunks: list[str]) -> None:
        """Configure chunks yielded by stream_text()."""
        self._text_chunks = list(chunks)

    def set_event_chunks(self, chunks: list[dict[str, object]]) -> None:
        """Configure events yielded by stream_events()."""
        self._event_chunks = [list(chunks)]

    async def complete_json(
        self,
        *,
        messages: list[LLMMessage],
        schema: type[Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> JsonObject:
        self._raise_if_failed()
        self.requests.append(messages)
        if not self.responses:
            return {"status": "ok"}
        return self.responses.pop(0)

    async def chat(
        self,
        *,
        messages: list[LLMMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        self._raise_if_failed()
        self.requests.append(messages)
        if not self.raw_responses:
            return "ok"
        return self.raw_responses.pop(0)

    async def stream_text(
        self,
        *,
        messages: list[LLMMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        self._raise_if_failed()
        self.stream_text_calls.append(messages)
        for chunk in self._text_chunks:
            yield chunk

    async def stream_events(
        self,
        *,
        messages: list[LLMMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        self._raise_if_failed()
        self.stream_events_calls.append(messages)
        for chunk in self._event_chunks:
            for event in chunk:
                yield event

    async def close(self) -> None:
        return None


class FakeEmbeddingProvider(FailureMixin, EmbeddingProviderPort):
    def __init__(self, dimension: int = 3, vector: EmbeddingVector | None = None) -> None:
        super().__init__()
        self.dimension = dimension
        self.vector = list(vector) if vector is not None else None
        self.requests: list[list[str]] = []
        self.texts: list[str] = []
        self.queries: list[str] = []
        self.query_task_descriptions: list[str] = []
        self._query_task_descriptions = self.query_task_descriptions
        self.document_batch_calls: int = 0

    async def embed(self, texts: list[str]) -> list[EmbeddingVector]:
        self._raise_if_failed()
        self.requests.append(texts)
        self.texts.extend(texts)
        self.document_batch_calls += 1
        if self.vector is not None:
            return [list(self.vector) for _ in texts]
        return [[float(index + 1)] * self.dimension for index, _text in enumerate(texts)]

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingVector]:
        return await self.embed(texts)

    async def embed_query(self, text: str, *, task_description: str = "") -> EmbeddingVector:
        self._raise_if_failed()
        self.queries.append(text)
        self.query_task_descriptions.append(task_description)
        if self.vector is not None:
            return list(self.vector)
        return [1.0] * self.dimension

    async def embed_documents(self, texts: list[str]) -> list[EmbeddingVector]:
        return await self.embed(texts)

    def reset(self) -> None:
        self.requests.clear()
        self.texts.clear()
        self.queries.clear()
        self.query_task_descriptions.clear()
        self.document_batch_calls = 0
        self._next_failure = None

    async def close(self) -> None:
        return None
