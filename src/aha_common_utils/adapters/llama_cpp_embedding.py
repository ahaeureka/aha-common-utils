"""Local embedding provider backed by llama-cpp-python + GGUF model.

Runs the Qwen3-Embedding-4B-GGUF model locally — no API calls,
no network dependency.  The model is loaded lazily on first use
and protected by a lock for thread-safe concurrent access.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, cast

from llama_cpp import Llama
from llama_cpp.llama_types import CreateEmbeddingResponse, Embedding

from aha_common_utils.ports.embedding_provider import EmbeddingProviderPort
from aha_common_utils.ports.provider_capability import ExecutionMode, ProviderCapability
from aha_common_utils.ports.types import EmbeddingVector


class LlamaCppEmbeddingProvider(EmbeddingProviderPort):
    """EmbeddingProviderPort backed by a local GGUF model via llama-cpp-python.

    Args:
        model_path: Path to the GGUF model file on disk.
        n_ctx: Context window size (default 512 — enough for short query/doc
            embeddings; Qwen3-Embedding uses at most 384 tokens).
        n_gpu_layers: Number of layers to offload to GPU (0 = CPU only).
        embedding_dimension: Expected output dimension.  Qwen3-Embedding-4B
            produces 2560-dimensional vectors.
        model_name: Human-readable model identifier reported via the
            ``model_name`` property (used by GraphRAG-SDK bridges).
        verbose: Enable llama.cpp verbose logging.
    """

    def __init__(
        self,
        *,
        model_path: str,
        n_ctx: int = 512,
        n_gpu_layers: int = 0,
        embedding_dimension: int = 2560,
        model_name: str = "qwen3-embedding-4b-gguf",
        verbose: bool = False,
    ) -> None:
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_gpu_layers = n_gpu_layers
        self._embedding_dimension = embedding_dimension
        self._model_name = model_name
        self._verbose = verbose
        self._model: Any = None
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            supported_modes=(ExecutionMode.ONLINE_MULTI_INPUT, ExecutionMode.BOUNDED_PARALLEL),
            max_items_per_batch=10,
            max_tokens_per_batch=16000,
        )

    def _load_model(self) -> Llama:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = Llama(
                        model_path=self._model_path,
                        embedding=True,
                        n_ctx=self._n_ctx,
                        n_gpu_layers=self._n_gpu_layers,
                        verbose=self._verbose,
                    )
        return self._model

    async def embed_query(
        self,
        text: str,
        *,
        task_description: str = "",
    ) -> EmbeddingVector:
        if task_description:
            text = self._make_instruct(task_description, text)
        results = await self._embed([text])
        return results[0] if results else [0.0]

    async def embed_documents(self, texts: list[str]) -> list[EmbeddingVector]:
        return await self._embed(texts)

    async def embed(self, texts: list[str]) -> list[EmbeddingVector]:
        return await self._embed(texts)

    async def _embed(self, texts: list[str]) -> list[EmbeddingVector]:
        if not texts:
            return []

        model = await asyncio.to_thread(self._load_model)
        response = cast(
            CreateEmbeddingResponse,
            await asyncio.to_thread(model.create_embedding, texts),
        )
        data: list[Embedding] | None = response.get("data")
        if not data:
            return [[0.0] * self._embedding_dimension for _ in texts]

        vectors: list[EmbeddingVector] = []
        for item in sorted(data, key=lambda x: x["index"]):
            raw = item["embedding"]
            if raw and isinstance(raw[0], list):
                nested = cast("list[list[float]]", raw)
                flat: list[float] = [v for sub in nested for v in sub]
                vectors.append(flat)
            else:
                vectors.append(cast("list[float]", raw))
        return vectors

    async def close(self) -> None:
        model = self._model
        if model is not None:
            with self._lock:
                self._model = None
            await asyncio.to_thread(model.close)

    def __del__(self) -> None:
        model = self._model
        if model is not None:
            try:
                model.close()
            except Exception:
                pass
