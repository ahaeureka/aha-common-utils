"""CamoufoxStrategy — Camoufox Firefox 指纹伪装策略（可选依赖）。"""

from __future__ import annotations

from typing import Any

from aha_common_utils.http_fetch.anti_detection import DEFAULT_HTTP_HEADERS, AntiDetectionStrategy


class CamoufoxStrategy(AntiDetectionStrategy):
    """基于 Camoufox 的真实 Firefox 指纹伪装策略。

    支持完整 JavaScript 渲染（SPA 站 / ``render: js``）。
    ``camoufox`` 为可选依赖：缺失时在 ``fetch`` 内抛 ``ImportError``。
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        proxy_url: str = "",
        headless: bool | str = "virtual",
        locale: str = "en-US",
        geoip: bool = False,
    ) -> None:
        self._page_timeout_ms = int(timeout_seconds * 1000)
        self._proxy_url = proxy_url
        self._headless = headless
        self._locale = locale
        self._geoip = geoip

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
        from camoufox.async_api import AsyncCamoufox

        effective_proxy = proxy_url or self._proxy_url
        launch_options: dict[str, Any] = {"headless": self._headless, "locale": self._locale}
        if self._geoip:
            launch_options["geoip"] = True
        if effective_proxy:
            launch_options["proxy"] = {"server": effective_proxy}

        async with AsyncCamoufox(**launch_options) as browser:
            page = await browser.new_page()
            if hasattr(page, "set_default_timeout"):
                page.set_default_timeout(self._page_timeout_ms)
            request_headers = {**DEFAULT_HTTP_HEADERS, **(headers or {})}
            await page.set_extra_http_headers(request_headers)
            await page.goto(url, wait_until="domcontentloaded")
            content = await page.content()
            final_url = str(getattr(page, "url", url))

        return (
            200,
            content,
            {"version": "camoufox", "url": url, "final_url": final_url},
        )
