"""CloakBrowserStrategy — CloakBrowser 浏览器级反检测策略（可选依赖）。"""

from __future__ import annotations

from typing import Any

from aha_common_utils.http_fetch.anti_detection import DEFAULT_HTTP_HEADERS, AntiDetectionStrategy


class CloakBrowserStrategy(AntiDetectionStrategy):
    """基于 CloakBrowser 的浏览器级反检测策略。

    使用 Chrome 指纹池，支持完整 JavaScript 渲染（SPA 站 / ``render: js``）。
    ``cloakbrowser`` 为可选依赖：缺失时在 ``fetch`` 内抛 ``ImportError``。
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        proxy_url: str = "",
        headless: bool | str = "virtual",
        locale: str = "en-US",
        geoip: bool = False,
        humanize: bool = True,
    ) -> None:
        self._page_timeout_ms = int(timeout_seconds * 1000)
        self._proxy_url = proxy_url
        self._headless = headless
        self._locale = locale
        self._geoip = geoip
        self._humanize = humanize

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
        from cloakbrowser import launch_async  # type: ignore[import-untyped]  # 可选依赖，无 py.typed 存根

        effective_proxy = proxy_url or self._proxy_url
        launch_options: dict[str, Any] = {"headless": self._headless, "locale": self._locale}
        if self._geoip:
            launch_options["geoip"] = True
        if self._humanize:
            launch_options["humanize"] = True
        if effective_proxy:
            launch_options["proxy"] = effective_proxy

        browser = await launch_async(**launch_options)
        try:
            page = await browser.new_page()
            if hasattr(page, "set_default_timeout"):
                page.set_default_timeout(self._page_timeout_ms)
            request_headers = {**DEFAULT_HTTP_HEADERS, **(headers or {})}
            await page.set_extra_http_headers(request_headers)
            await page.goto(url, wait_until="domcontentloaded")
            content = await page.content()
            final_url = str(getattr(page, "url", url))
        finally:
            await browser.close()

        return (
            200,
            content,
            {"version": "cloakbrowser", "url": url, "final_url": final_url},
        )
