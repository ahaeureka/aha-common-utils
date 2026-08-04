"""AntiDetectionManager — 反检测策略链与自动降级。

按站点画像指定的策略顺序尝试，命中反爬信号或异常时自动降级到下一策略；
单次请求命中反爬且未走代理时，优先经 ProxyManager 换出口代理重试一次。
可选依赖（curl-cffi / cloakbrowser / camoufox）采用延迟导入 + 运行时依赖
检测：依赖缺失抛 ImportError，由 manager 捕获后跳过该策略继续降级。
"""

from __future__ import annotations

import asyncio
import re
import time
from abc import ABC, abstractmethod
from typing import Any

from aha_common_utils.http_fetch.anti_crawl_detector import AntiCrawlDetector, SiteProfile
from aha_common_utils.http_fetch.auto_planning import AutoPlanningEngine
from aha_common_utils.http_fetch.proxy import ProxyManager
from aha_common_utils.ports.http_fetch import (
    AntiCrawlSignal,
    HttpFetchError,
    HttpFetchPort,
    HttpFetchRequest,
    HttpFetchResponse,
)

DEFAULT_HTTP_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class AntiDetectionStrategy(ABC):
    """反检测策略基类。"""

    @abstractmethod
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
        """发起请求，返回 ``(status_code, body, extra)``。"""
        ...


def _extract_domain(url: str) -> str:
    """从 URL 中提取域名。"""
    match = re.match(r"https?://([^/?#:]+)", url)
    return match.group(1) if match else url


def redact_proxy_url(proxy_url: str) -> str:
    """脱敏代理 URL：隐藏认证凭据，仅保留协议与主机部分。"""
    if not proxy_url:
        return ""
    match = re.match(r"^([a-z]+://)([^@/]+)@(.*)$", proxy_url, re.IGNORECASE)
    if match:
        return f"{match.group(1)}***@{match.group(3)}"
    return proxy_url


def build_default_strategies() -> list[AntiDetectionStrategy]:
    """构造默认策略链（延迟导入可选依赖）。

    顺序：CurlCffiStrategy（TLS 指纹）→ CloakBrowserStrategy → CamoufoxStrategy。
    httpx 是裸 HTTP 客户端、TLS 指纹弱于 curl-cffi，不进入默认链路；需要时可
    通过 ``HttpFetchProviderConfig.strategy_order`` 显式加入。
    """
    from aha_common_utils.adapters.http_camoufox import CamoufoxStrategy
    from aha_common_utils.adapters.http_cloakbrowser import CloakBrowserStrategy
    from aha_common_utils.adapters.http_curl_cffi import CurlCffiStrategy

    return [
        CurlCffiStrategy(),
        CloakBrowserStrategy(),
        CamoufoxStrategy(),
    ]


def _response_headers(extra: dict[str, Any]) -> dict[str, Any] | None:
    """从策略 extra 中提取响应头（若有）。"""
    raw = extra.get("headers")
    return raw if isinstance(raw, dict) else None


class AntiDetectionManager(HttpFetchPort):
    """按站点画像策略链自动降级的统一请求入口。"""

    def __init__(
        self,
        strategies: list[AntiDetectionStrategy] | None = None,
        detector: AntiCrawlDetector | None = None,
        planning: AutoPlanningEngine | None = None,
        proxy_manager: ProxyManager | None = None,
        max_concurrency: int = 5,
    ) -> None:
        self._strategies = list(strategies if strategies is not None else build_default_strategies())
        self._detector = detector or AntiCrawlDetector()
        self._planning = planning or AutoPlanningEngine()
        self._proxy_manager = proxy_manager
        self._semaphore = asyncio.Semaphore(max(max_concurrency, 1))

    def register_site(self, profile: SiteProfile) -> None:
        """注册站点反爬画像，委托给 detector。"""
        self._detector.register_site(profile)

    async def fetch(self, request: HttpFetchRequest) -> HttpFetchResponse:
        """按站点画像的策略顺序发起请求，命中反爬时自动降级。"""
        domain = request.domain or _extract_domain(request.url)
        profile = self._detector.get_site_profile(domain)
        strategies = self._ordered_strategies(profile)

        proxy_url = ""
        if profile and profile.use_proxy and self._proxy_manager is not None:
            proxy_url = (await self._proxy_manager.get_proxy()) or ""

        delay = await self._planning.on_request()
        if delay > 0:
            await asyncio.sleep(delay)

        async with self._semaphore:
            return await self._run_strategy_chain(request, domain, strategies, proxy_url)

    def _ordered_strategies(self, profile: SiteProfile | None) -> list[AntiDetectionStrategy]:
        """按站点推荐的策略顺序排序；站点未指定时使用默认顺序。"""
        if profile and profile.strategy_order:
            by_name = {type(strategy).__name__: strategy for strategy in self._strategies}
            ordered = [by_name[name] for name in profile.strategy_order if name in by_name]
            if ordered:
                return ordered
        return list(self._strategies)

    async def _run_strategy_chain(
        self,
        request: HttpFetchRequest,
        domain: str,
        strategies: list[AntiDetectionStrategy],
        initial_proxy_url: str,
    ) -> HttpFetchResponse:
        proxy_url = initial_proxy_url
        proxy_retried = False
        last_blocked: HttpFetchResponse | None = None
        last_error: Exception | None = None
        attempts = 0
        index = 0

        while index < len(strategies):
            strategy = strategies[index]
            strategy_name = type(strategy).__name__
            try:
                start = time.perf_counter()
                status_code, body, extra = await strategy.fetch(
                    request.url,
                    method=request.method,
                    headers=dict(request.headers),
                    body=request.body,
                    proxy_url=proxy_url,
                    timeout_seconds=request.timeout_seconds,
                )
                latency_ms = (time.perf_counter() - start) * 1000.0
                attempts += 1
                await self._planning.on_response(status_code)
                signal, detail = self._detector.detect(
                    status_code,
                    body,
                    headers=_response_headers(extra),
                    domain=domain,
                )
                response = HttpFetchResponse(
                    status_code=status_code,
                    body=body,
                    final_url=str(extra.get("final_url") or request.url),
                    strategy_used=strategy_name,
                    anti_crawl_signal=signal,
                    proxy_used=redact_proxy_url(proxy_url),
                    attempt_count=attempts,
                    latency_ms=latency_ms,
                    extra={**extra, "detect_detail": detail},
                )
                if signal is AntiCrawlSignal.NONE:
                    return response
                last_blocked = response
                if not proxy_retried and not proxy_url and self._proxy_manager is not None:
                    proxy_retried = True
                    proxy_url = (await self._proxy_manager.get_proxy()) or ""
                    if proxy_url:
                        continue
                index += 1
            except ImportError:
                index += 1
                continue
            except Exception as exc:  # noqa: BLE001
                attempts += 1
                last_error = exc
                index += 1

        if last_blocked is not None:
            return last_blocked
        raise HttpFetchError(f"all strategies failed for {request.url}") from last_error

    async def close(self) -> None:
        """释放底层资源（策略资源由各自实现管理）。"""
        return None
