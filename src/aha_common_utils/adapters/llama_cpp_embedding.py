"""Local embedding provider backed by llama-cpp-python + GGUF model.

Runs the Qwen3-Embedding-4B-GGUF model locally — no API calls,
no network dependency.  The model is loaded lazily on first use
and protected by a lock for thread-safe concurrent access.
"""

from __future__ import annotations

import asyncio
import math
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
        embedding_dimension: Requested output dimension.  Qwen3-Embedding-4B
            natively produces 2560 dimensions and is trained with MRL
            (Matryoshka), so a *smaller* target truncates the vector to its
            first N entries and re-normalises — the model card states
            "supports user-defined output dimensions ranging from 32 to 2560".
            A target larger than the native width is rejected instead of padded.
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
                vectors.append(self._fit_dimension(flat))
            else:
                vectors.append(self._fit_dimension(cast("list[float]", raw)))
        return vectors

    def _fit_dimension(self, vector: list[float]) -> EmbeddingVector:
        """把原生维度裁到请求维度（MRL），并重新 L2 归一化。

        截断后必须重新归一化：MRL 的前 N 维是"可截断"的近似，但截断会改变范数，
        不归一化会让余弦相似度与未截断向量不可比。请求维度大于原生维度时直接报错
        ——补零会让不同文本的向量在补齐维度上完全一致，等于伪造相似度。
        """
        target = self._embedding_dimension
        native = len(vector)
        if target == native:
            return vector
        if target > native:
            raise ValueError(
                f"requested embedding_dimension={target} exceeds the model's native "
                f"dimension {native}; padding would fabricate similarity, so pick a "
                f"smaller target or another model"
            )
        truncated = vector[:target]
        norm = math.sqrt(sum(v * v for v in truncated))
        if norm == 0.0:
            return truncated
        return [v / norm for v in truncated]

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
