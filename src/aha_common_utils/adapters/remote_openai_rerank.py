"""远程 OpenAI 兼容 rerank adapter（``/v1/rerank``）。"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from aha_common_utils.ports.rerank_provider import RerankProviderPort, RerankScore


class AsyncPostClient(Protocol):
    """最小化的异步 POST 客户端契约，便于测试注入。"""

    async def post(
        self,
        url: str,
        *,
        data: dict[str, object] | None = None,
        json: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """发送异步 POST 请求，返回带 ``status_code``/``json()`` 的响应对象。"""


class RerankServiceError(RuntimeError):
    """远程 rerank 服务无法产生可用响应时抛出。"""


class RemoteOpenAIRerankProvider(RerankProviderPort):
    """调用 OpenAI 兼容 ``/v1/rerank`` 端点的 rerank 提供者。

    Args:
        api_url: 基础 URL（例如 ``http://localhost:4000/v1``）。
        api_key: Bearer API 密钥。
        model: 用于 rerank 的模型名称。
        request_timeout_seconds: 请求超时。
        http_client: 可注入的异步 POST 客户端（测试用）。
    """

    def __init__(
        self,
        *,
        api_url: str,
        api_key: str,
        model: str,
        request_timeout_seconds: float = 60.0,
        http_client: AsyncPostClient | None = None,
    ) -> None:
        if not api_url.strip():
            raise ValueError("api_url must not be empty")
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        if not model.strip():
            raise ValueError("model must not be empty")
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._request_timeout_seconds = request_timeout_seconds
        self._http_client = http_client or httpx.AsyncClient(timeout=request_timeout_seconds)

    async def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_k: int | None = None,
    ) -> list[RerankScore]:
        if not documents:
            return []
        payload: dict[str, object] = {
            "model": self._model,
            "query": query,
            "documents": documents,
        }
        if top_k is not None:
            payload["top_n"] = top_k

        response = await self._http_client.post(
            f"{self._api_url}/rerank",
            json=payload,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=self._request_timeout_seconds,
        )
        if response.status_code != 200:
            raise RerankServiceError(
                f"rerank service returned HTTP {response.status_code}: {response.text}"
            )
        body = response.json()
        results = body.get("results", []) if isinstance(body, dict) else []
        scores = [
            RerankScore(index=int(item["index"]), score=float(item["relevance_score"]))
            for item in results
        ]
        scores.sort(key=lambda s: s.score, reverse=True)
        return scores

    async def close(self) -> None:
        close_fn = getattr(self._http_client, "aclose", None)
        if close_fn is not None:
            await close_fn()
