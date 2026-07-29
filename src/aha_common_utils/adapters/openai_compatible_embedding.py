"""OpenAI-compatible embeddings adapter backed by LangChain."""

from __future__ import annotations

from typing import Any

from pydantic import SecretStr

from aha_common_utils.ports.embedding_provider import EmbeddingProviderPort
from aha_common_utils.ports.types import EmbeddingVector
from aha_common_utils.register import ProviderRegistry
from aha_common_utils.tracing import get_tracer

_tracer = get_tracer("openai_compatible_embedding")


@ProviderRegistry.register("openai-compatible-embedding", singleton=False)
class OpenAICompatibleEmbeddingProvider(EmbeddingProviderPort):
    """EmbeddingProviderPort backed by an OpenAI-compatible embeddings API, using LangChain."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        request_timeout_seconds: float = 60.0,
        embedding_model: Any = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._request_timeout_seconds = request_timeout_seconds
        self._embedding_model: Any = embedding_model or self._build_embedding_model()

    @property
    def model_name(self) -> str:
        """Return the configured embedding model name."""
        return self._model

    def _build_embedding_model(self) -> Any:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=self._model,
            api_key=SecretStr(self._api_key),
            base_url=self._base_url,
            timeout=self._request_timeout_seconds,
        )

    # ── EmbeddingProviderPort ──────────────────────────────────────────

    async def embed(self, texts: list[str]) -> list[EmbeddingVector]:
        """Generate embeddings for input texts (legacy entry point)."""
        return await self.embed_texts(texts)

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingVector]:
        """Embed input texts and preserve caller input order."""
        if not texts:
            return []

        with _tracer.start_as_current_span("embedding.embed_texts") as span:
            span.set_attribute("embedding.model", self._model)
            span.set_attribute("embedding.text_count", len(texts))
            try:
                vectors = await self._embedding_model.aembed_documents(texts)
            except Exception as exc:
                span.record_exception(exc)
                raise

        result: list[EmbeddingVector] = [list(v) for v in vectors]
        return result

    async def close(self) -> None:
        close_fn = getattr(self._embedding_model, "close", None)
        if close_fn is not None:
            result = close_fn()
            if result is not None and hasattr(result, "__await__"):
                await result
