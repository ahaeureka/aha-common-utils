"""本地 llama.cpp GGUF cross-encoder rerank 骨架。

使用 ``Llama(pooling_type=LLAMA_POOLING_TYPE_RANK)`` 加载 Qwen3-Reranker 类
cross-encoder GGUF 模型。llama-cpp-python 0.3.34 没有高层 ``rerank()`` API，
完整打分需基于底层 ``llama_encode`` 逐对调用实现，并依赖真实模型验证。

当前实现提供组件骨架：构造参数、惰性加载、池化类型与模型路径校验。打分逻辑
标为待真实模型端到端验证，因此 ``rerank`` 在模型加载路径未验证前抛出
``NotImplementedError``，避免返回未经校验的相关性分数。
"""

from __future__ import annotations

from typing import Any

from llama_cpp import Llama
from llama_cpp import llama_cpp as _llama_cpp

from aha_common_utils.ports.rerank_provider import RerankProviderPort, RerankScore

_RANK_POOLING_TYPE = _llama_cpp.LLAMA_POOLING_TYPE_RANK


class LlamaCppRerankProvider(RerankProviderPort):
    """基于本地 GGUF cross-encoder 的 rerank 提供者骨架。

    Args:
        model_path: 磁盘上的 GGUF 模型文件路径。
        n_ctx: 上下文窗口大小。
        n_gpu_layers: 卸载到 GPU 的层数（0 = 仅 CPU）。
        verbose: 启用 llama.cpp 详细日志。
    """

    def __init__(
        self,
        *,
        model_path: str,
        n_ctx: int = 512,
        n_gpu_layers: int = 0,
        verbose: bool = False,
    ) -> None:
        if not model_path.strip():
            raise ValueError("model_path must not be empty")
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_gpu_layers = n_gpu_layers
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
                verbose=self._verbose,
            )
        return self._model

    async def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_k: int | None = None,
    ) -> list[RerankScore]:
        # 骨架阶段：真实模型尚未下载，无法端到端验证逐对打分。
        # 完整实现应基于 `llama_encode` 对 (query, doc) 逐对计算 rank logit，
        # 并按分数降序返回 RerankScore。
        raise NotImplementedError(
            "llama-cpp rerank scoring is pending real-model verification; "
            "use the remote OpenAI-compatible rerank provider instead."
        )

    async def close(self) -> None:
        model = self._model
        if model is not None:
            self._model = None
            try:
                model.close()
            except Exception:  # pragma: no cover - best-effort shutdown
                pass
