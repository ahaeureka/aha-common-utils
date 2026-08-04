"""RerankProviderPort — 检索结果的二次排序契约。

两阶段检索中的第二阶段：对 ``query`` 与候选 ``documents`` 打分并重排，
用于在 top-k 有限预算下提升方法/证据/Skill 路由的命中精度。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RerankScore:
    """单个候选文档的重排分数。"""

    index: int
    score: float


class RerankProviderPort(ABC):
    """对候选文档进行重排的端口契约。

    实现可以是远程 OpenAI 兼容 rerank 服务，也可以是本地 GGUF
    cross-encoder（llama.cpp ``LLAMA_POOLING_TYPE_RANK``）。
    """

    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_k: int | None = None,
    ) -> list[RerankScore]:
        """按相关性对候选文档打分并返回按分数降序排列的结果。

        Args:
            query: 查询文本。
            documents: 候选文档列表，按原顺序保留 ``index``。
            top_k: 返回的最大结果数；为 ``None`` 时返回全部。

        Returns:
            按分数降序排列的 :class:`RerankScore` 列表。
        """
