"""本地 llama.cpp GGUF cross-encoder rerank。

使用 ``Llama(pooling_type=LLAMA_POOLING_TYPE_RANK, embedding=True)`` 加载
Qwen3-Reranker 类 cross-encoder GGUF 模型。llama-cpp-python 0.3.34 没有高层
``rerank()`` API，因此复用 ``embed()``：将 (query, document) 拼接为单个输入
序列，RANK pooling 下每个序列输出相关性 logit，取向量首元素作为分数。

打分路径基于 llama.cpp 的 RANK pooling 语义实现；真实模型下载后应通过
端到端评测验证分数单调性与排序质量（见技术方案 11.4.1 门禁）。
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

from llama_cpp import Llama
from llama_cpp import llama_cpp as _llama_cpp

from aha_common_utils.ports.rerank_provider import RerankProviderPort, RerankScore

_RANK_POOLING_TYPE = _llama_cpp.LLAMA_POOLING_TYPE_RANK


class LlamaCppRerankProvider(RerankProviderPort):
    """基于本地 GGUF cross-encoder 的 rerank 提供者。

    Args:
        model_path: 磁盘上的 GGUF 模型文件路径。
        n_ctx: 上下文窗口大小。
        n_gpu_layers: 卸载到 GPU 的层数（0 = 仅 CPU）。
        pair_separator: 拼接 query 与 document 时使用的分隔符。
        verbose: 启用 llama.cpp 详细日志。
    """

    def __init__(
        self,
        *,
        model_path: str,
        n_ctx: int = 512,
        n_gpu_layers: int = 0,
        pair_separator: str = "\n",
        verbose: bool = False,
    ) -> None:
        if not model_path.strip():
            raise ValueError("model_path must not be empty")
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_gpu_layers = n_gpu_layers
        self._pair_separator = pair_separator
        self._verbose = verbose
        self._model: Any | None = None

    @property
    def _pooling_type_name(self) -> str:
        return "RANK"

    def _load_model(self) -> Llama:
        if self._model is None:
            self._model = Llama(
                model_path=self._model_path,
                n_ctx=self._n_ctx,
                n_gpu_layers=self._n_gpu_layers,
                pooling_type=_RANK_POOLING_TYPE,
                embedding=True,
                verbose=self._verbose,
            )
        return self._model

    def _make_pair(self, query: str, document: str) -> str:
        return f"{query}{self._pair_separator}{document}"

    def _scores_from_embeddings(self, embeddings: list[list[float]]) -> list[float]:
        """从 RANK pooling 的每序列输出中提取相关性分数。

        RANK pooling 下每个 (query, document) 序列输出一个相关性 logit 向量，
        取首元素作为该文档的分数。
        """
        scores: list[float] = []
        for embedding in embeddings:
            if embedding:
                scores.append(float(embedding[0]))
            else:
                scores.append(0.0)
        return scores

    async def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_k: int | None = None,
    ) -> list[RerankScore]:
        if not documents:
            return []

        model = await asyncio.to_thread(self._load_model)
        pairs = [self._make_pair(query, document) for document in documents]
        # ``embed`` 对 list 输入总是返回 list[list[float]]；显式 cast 以满足静态类型。
        embeddings = cast("list[list[float]]", await asyncio.to_thread(model.embed, pairs))
        scores = self._scores_from_embeddings(embeddings)

        results = [
            RerankScore(index=index, score=score)
            for index, score in enumerate(scores)
        ]
        results.sort(key=lambda item: item.score, reverse=True)
        if top_k is not None:
            results = results[:top_k]
        return results

    async def close(self) -> None:
        model = self._model
        if model is not None:
            self._model = None
            try:
                model.close()
            except Exception:  # pragma: no cover - best-effort shutdown
                pass
