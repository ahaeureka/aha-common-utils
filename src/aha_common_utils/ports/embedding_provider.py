"""Rich embedding generation contract.

Canonical ``EmbeddingProviderPort`` supporting instruction-tuned query
prefixes (Qwen3-Embedding convention), document/query split, and declared
``ProviderCapability`` for batch scheduling.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from aha_common_utils.ports.provider_capability import ExecutionMode, ProviderCapability
from aha_common_utils.ports.types import EmbeddingVector


class EmbeddingProviderPort(ABC):
    """Embedding generation contract.

    Subclasses SHOULD override :meth:`embed_query` and :meth:`embed_documents`
    so the caller can supply a task description for models that require
    instruction-tuned query prefixes (e.g. Qwen3-Embedding).
    The legacy :meth:`embed` is kept for backward compatibility and delegates
    to ``embed_documents`` by default.
    """

    @property
    def capability(self) -> ProviderCapability:
        """Declared provider capability.

        Default: online_multi_input (embedding providers naturally batch).
        """
        return ProviderCapability(
            supported_modes=(ExecutionMode.ONLINE_MULTI_INPUT,),
            max_items_per_batch=100,
            max_tokens_per_batch=64000,
        )

    # ── concrete defaults (no breaking change for existing adapters) ──────────

    @staticmethod
    def _make_instruct(task_description: str, query: str) -> str:
        """Wrap a query with a task instruction prefix for Qwen3-style models.

        Conforms to the Qwen3-Embedding ``get_detailed_instruct`` convention:
        ``Instruct: {task_description}\\nQuery:{query}``
        """
        return f"Instruct: {task_description}\nQuery: {query}"

    async def embed_query(
        self,
        text: str,
        *,
        task_description: str = "",
    ) -> EmbeddingVector:
        """Embed a single query string.

        When *task_description* is non-empty and the model supports
        instruction prefixes, the implementation SHOULD prepend the
        instruction before encoding.  The default falls back to a plain
        ``embed`` call.
        """
        results = await self.embed([text])
        return results[0] if results else [0.0]

    async def embed_documents(self, texts: list[str]) -> list[EmbeddingVector]:
        """Embed document texts (no instruction prefix)."""
        return await self.embed(texts)

    # ── legacy (kept for old-style callers) ───────────────────────────────────

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[EmbeddingVector]:
        """Generate embeddings for input texts."""

    @abstractmethod
    async def close(self) -> None:
        """Release resources."""
