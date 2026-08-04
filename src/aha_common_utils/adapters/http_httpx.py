"""HttpxStrategy — httpx 兜底策略（无特殊依赖）。"""

from __future__ import annotations

from typing import Any

import httpx

from aha_common_utils.http_fetch.anti_detection import DEFAULT_HTTP_HEADERS, AntiDetectionStrategy


class HttpxStrategy(AntiDetectionStrategy):
    """基于 httpx 的兜底策略。

    无需额外依赖，当 curl-cffi 不可用或需要更高层控制时使用。
    """

    def __init__(self, *, timeout_seconds: float = 30.0, proxy_url: str = "") -> None:
        self._timeout_seconds = timeout_seconds
        self._proxy_url = proxy_url

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        proxy_url: str = "",
        timeout_seconds: float = 30.0,
        **kwargs: Any,
    ) -> tuple[int, str, dict[str, Any]]:
        effective_proxy = proxy_url or self._proxy_url
        request_headers = {**DEFAULT_HTTP_HEADERS, **(headers or {})}
        client_kwargs: dict[str, Any] = {
            "headers": request_headers,
            "timeout": timeout_seconds or self._timeout_seconds,
            "follow_redirects": True,
        }
        if effective_proxy:
            client_kwargs["proxy"] = effective_proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.request(method, url, content=body)

        return (
            response.status_code,
            response.text,
            {
                "version": "httpx",
                "url": url,
                "final_url": str(response.url),
                "status_code": response.status_code,
                "headers": {key: value for key, value in response.headers.items()},
            },
        )
