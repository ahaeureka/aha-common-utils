"""TreeNavProviderPort — 话题树导航候选的 LLM 相关性辅助排序契约。

设计（topic-tree Slice 4）：LLM 只对「树导航候选集合」（t 通道命中的文档）
做相关性辅助排序，不参与边界判定 / 聚类 / 评分聚合主干。未注入 provider 时
由 ``TreeNavBoundary`` 确定性退化（原样返回），检索主路径可用性优先。
与 :class:`RerankProviderPort`（rerank_boundary 模式）同构：给定查询与候选
文档列表，返回按相关性降序的分数结果。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TreeNavScore:
    """单个树导航候选的 LLM 相关性分数。"""

    index: int
    score: float


class TreeNavProviderPort(ABC):
    """对树导航候选集合进行 LLM 相关性辅助排序的端口契约。

    实现为远程 OpenAI 兼容 LLM（``remote-openai``），仅作候选相关性排序的
    增强手段；未注入 / 异常时确定性退化，不影响分数聚合主干。
    """

    @abstractmethod
    async def navigate(
        self,
        query: str,
        candidates: list[str],
        *,
        top_k: int | None = None,
    ) -> list[TreeNavScore]:
        """按相关性对树导航候选打分并返回按分数降序排列的结果。

        Args:
            query: 查询文本。
            candidates: 树导航候选文档 ID 列表，按原顺序保留 ``index``。
            top_k: 返回的最大结果数；为 ``None`` 时返回全部。

        Returns:
            按分数降序排列的 :class:`TreeNavScore` 列表。
        """
