"""OpenAI-compatible embeddings adapter."""

from __future__ import annotations

from typing import Protocol, cast

from aha_common_utils.ports.llm_provider import EmbeddingProviderPort
from aha_common_utils.ports.types import EmbeddingVector
from aha_common_utils.register import ProviderRegistry


class OpenAIEmbeddings(Protocol):
    async def create(self, **kwargs: object) -> object:
        """Create embeddings."""


class OpenAIEmbeddingClient(Protocol):
    embeddings: OpenAIEmbeddings

    async def close(self) -> None:
        """Close the client."""


@ProviderRegistry.register("openai-compatible-embedding", singleton=False)
class OpenAICompatibleEmbeddingProvider(EmbeddingProviderPort):
    """EmbeddingProviderPort backed by an OpenAI-compatible embeddings API."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        request_timeout_seconds: float = 60.0,
        client: OpenAIEmbeddingClient | None = None,
    ) -> None:
        self._model = model
        self._client: OpenAIEmbeddingClient = client or self._build_client(
            base_url=base_url,
            api_key=api_key,
            request_timeout_seconds=request_timeout_seconds,
        )

    @property
    def model_name(self) -> str:
        """Return the configured embedding model name."""
        return self._model

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingVector]:
        """Embed input texts and preserve caller input order."""
        if not texts:
            return []
        response = await self._client.embeddings.create(model=self._model, input=texts)
        data = getattr(response, "data", None)
        if not data:
            return [[0.0] for _ in texts]
        index_map: dict[int, EmbeddingVector] = {}
        for item in data:
            index = int(getattr(item, "index", -1))
            if index in index_map:
                raise ValueError(f"duplicate embedding index {index} in API response")
            index_map[index] = list(getattr(item, "embedding", []))
        expected = set(range(len(texts)))
        found = set(index_map.keys())
        missing = expected - found
        if missing:
            raise ValueError(f"missing embedding index {sorted(missing)} in API response")
        return [index_map[index] for index in range(len(texts))]

    async def close(self) -> None:
        """Close the underlying OpenAI client when supported."""
        close = getattr(self._client, "close", None)
        if close is not None:
            await close()

    def _build_client(
        self,
        *,
        base_url: str,
        api_key: str,
        request_timeout_seconds: float,
    ) -> OpenAIEmbeddingClient:
        from openai import AsyncOpenAI

        return cast(OpenAIEmbeddingClient, AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=request_timeout_seconds))
