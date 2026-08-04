"""CurlCffiStrategy — curl-cffi TLS 指纹伪装策略（可选依赖）。"""

from __future__ import annotations

import random
from typing import Any, cast

from aha_common_utils.http_fetch.anti_detection import DEFAULT_HTTP_HEADERS, AntiDetectionStrategy

_BROWSER_FINGERPRINTS: dict[str, str] = {
    "chrome": "chrome120",
    "firefox": "firefox110",
    "edge": "edge101",
    "safari": "safari15_2",
}


class CurlCffiStrategy(AntiDetectionStrategy):
    """基于 curl-cffi 的 TLS 指纹伪装策略，降低被识别为爬虫的风险。

    ``curl_cffi`` 为可选依赖：缺失时在 ``fetch`` 内抛 ``ImportError``，
    由 AntiDetectionManager 捕获后跳过该策略继续降级。
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        proxy_url: str = "",
        default_browser: str = "chrome",
        impersonate_random: bool = True,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._proxy_url = proxy_url
        self._default_browser = default_browser
        self._impersonate_random = impersonate_random

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
        from curl_cffi import AsyncSession

        browser = random.choice(list(_BROWSER_FINGERPRINTS)) if self._impersonate_random else self._default_browser
        impersonate = _BROWSER_FINGERPRINTS[browser]
        effective_proxy = proxy_url or self._proxy_url
        request_headers = {**DEFAULT_HTTP_HEADERS, **(headers or {})}
        request_kwargs: dict[str, Any] = {
            "impersonate": impersonate,
            "headers": request_headers,
            "allow_redirects": True,
            "timeout": timeout_seconds or self._timeout_seconds,
        }
        if body:
            request_kwargs["data"] = body
        if effective_proxy:
            request_kwargs["proxies"] = {"http": effective_proxy, "https": effective_proxy}

        async with AsyncSession() as session:
            response = await session.request(cast(Any, method), url, **request_kwargs)

        return (
            response.status_code,
            response.text,
            {
                "version": "curl_cffi",
                "impersonate": impersonate,
                "url": url,
                "final_url": str(response.url),
                "status_code": response.status_code,
                "headers": {key: value for key, value in response.headers.items()},
            },
        )
