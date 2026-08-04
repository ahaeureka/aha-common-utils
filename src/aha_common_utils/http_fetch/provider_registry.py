"""Typed registry helpers for HTTP fetch providers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import cast

from aha_common_utils.http_fetch.anti_crawl_detector import AntiCrawlDetector
from aha_common_utils.http_fetch.anti_detection import AntiDetectionManager, AntiDetectionStrategy
from aha_common_utils.http_fetch.auto_planning import AutoPlanningEngine
from aha_common_utils.http_fetch.proxy import ProxyManager
from aha_common_utils.ports.http_fetch import (
    HttpFetchPort,
    HttpFetchRequest,
    HttpFetchResponse,
)
from aha_common_utils.runtime.provider_registry import (
    UnknownProviderError,
    available_provider_names,
    create_provider_instance,
    register_provider_class,
)

_STRATEGY_NAMES = ("curl-cffi", "cloakbrowser", "camoufox")


@dataclass(frozen=True, slots=True)
class HttpFetchProviderConfig:
    """HTTP fetch provider creation parameters.

    默认策略：以 CurlCffiHttpFetchProvider（TLS 指纹伪装）为首选，请求失败
    （反爬信号 / 异常 / 可选依赖缺失）时沿 ``strategy_order`` 逐步升级：
    ``curl-cffi → cloakbrowser → camoufox``。httpx 保留为可显式选择的单策略
    provider，但不在默认链路内（curl-cffi 的 TLS 指纹严格强于裸 httpx）。
    """

    provider: str = "anti-detection"
    strategy_order: tuple[str, ...] = _STRATEGY_NAMES
    timeout_seconds: float = 30.0
    proxy_urls: tuple[str, ...] = ()
    max_rate: float = 5.0
    min_rate: float = 0.1
    max_concurrency: int = 5


class UnknownHttpFetchProviderError(ValueError):
    """Raised when no HTTP fetch provider is registered for the requested name."""


class StrategyHttpFetchProvider(HttpFetchPort):
    """把单个 AntiDetectionStrategy 包装为 HttpFetchPort 契约。"""

    def __init__(self, *, strategy: AntiDetectionStrategy, detector: AntiCrawlDetector | None = None) -> None:
        self._strategy = strategy
        self._detector = detector or AntiCrawlDetector()

    async def fetch(self, request: HttpFetchRequest) -> HttpFetchResponse:
        start = time.perf_counter()
        status_code, body, extra = await self._strategy.fetch(
            request.url,
            method=request.method,
            headers=dict(request.headers),
            body=request.body,
            timeout_seconds=request.timeout_seconds,
        )
        latency_ms = (time.perf_counter() - start) * 1000.0
        response_headers = extra.get("headers") if isinstance(extra.get("headers"), dict) else None
        signal, detail = self._detector.detect(status_code, body, headers=response_headers, domain=request.domain or "")
        return HttpFetchResponse(
            status_code=status_code,
            body=body,
            final_url=str(extra.get("final_url") or request.url),
            strategy_used=type(self._strategy).__name__,
            anti_crawl_signal=signal,
            attempt_count=1,
            latency_ms=latency_ms,
            extra={**extra, "detect_detail": detail},
        )

    async def close(self) -> None:
        return None


class HttpxHttpFetchProvider(StrategyHttpFetchProvider):
    """单策略 httpx provider。"""

    def __init__(self, *, timeout_seconds: float = 30.0, detector: AntiCrawlDetector | None = None) -> None:
        from aha_common_utils.adapters.http_httpx import HttpxStrategy

        super().__init__(strategy=HttpxStrategy(timeout_seconds=timeout_seconds), detector=detector)


class CurlCffiHttpFetchProvider(StrategyHttpFetchProvider):
    """单策略 curl-cffi provider。"""

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        impersonate_random: bool = True,
        detector: AntiCrawlDetector | None = None,
    ) -> None:
        from aha_common_utils.adapters.http_curl_cffi import CurlCffiStrategy

        super().__init__(
            strategy=CurlCffiStrategy(timeout_seconds=timeout_seconds, impersonate_random=impersonate_random),
            detector=detector,
        )


def register_http_fetch_provider(name: str, provider_cls: type[HttpFetchPort]) -> type[HttpFetchPort]:
    """Register a non-singleton HTTP fetch provider implementation."""
    return register_provider_class(name, provider_cls)


def available_http_fetch_providers() -> tuple[str, ...]:
    """Return provider names registered for HttpFetchPort plus the default anti-detection."""
    _ensure_builtin_providers()
    names = {"anti-detection", *available_provider_names(HttpFetchPort)}
    return tuple(sorted(names))


def create_http_fetch_provider(config: HttpFetchProviderConfig) -> HttpFetchPort:
    """Create an HTTP fetch provider from typed config.

    默认 provider ``anti-detection`` 对应 AntiDetectionManager；未注册的
    provider 抛 UnknownHttpFetchProviderError，fail-fast，不回退到 Fake。
    """
    _ensure_builtin_providers()
    if config.provider == "anti-detection":
        return _build_anti_detection_manager(config)
    try:
        return cast(
            HttpFetchPort,
            create_provider_instance(
                config.provider, HttpFetchPort, parameters={"timeout_seconds": config.timeout_seconds}
            ),
        )
    except UnknownProviderError as exc:
        raise UnknownHttpFetchProviderError(f"unknown HTTP fetch provider: {config.provider}") from exc


def register_builtin_http_fetch_providers() -> None:
    """Register HTTP fetch providers shipped by aha-common-utils."""
    if "httpx" not in available_provider_names(HttpFetchPort):
        register_http_fetch_provider("httpx", HttpxHttpFetchProvider)
    if "curl-cffi" not in available_provider_names(HttpFetchPort):
        register_http_fetch_provider("curl-cffi", CurlCffiHttpFetchProvider)


def _ensure_builtin_providers() -> None:
    register_builtin_http_fetch_providers()


def _build_anti_detection_manager(config: HttpFetchProviderConfig) -> AntiDetectionManager:
    from aha_common_utils.adapters.http_camoufox import CamoufoxStrategy
    from aha_common_utils.adapters.http_cloakbrowser import CloakBrowserStrategy
    from aha_common_utils.adapters.http_curl_cffi import CurlCffiStrategy
    from aha_common_utils.adapters.http_httpx import HttpxStrategy

    strategy_classes = {
        "curl-cffi": CurlCffiStrategy,
        "httpx": HttpxStrategy,
        "cloakbrowser": CloakBrowserStrategy,
        "camoufox": CamoufoxStrategy,
    }
    strategies: list[AntiDetectionStrategy] = [
        strategy_classes[name](timeout_seconds=config.timeout_seconds)
        for name in config.strategy_order
        if name in strategy_classes
    ]
    return AntiDetectionManager(
        strategies=strategies,
        planning=AutoPlanningEngine(max_rate=config.max_rate, min_rate=config.min_rate),
        proxy_manager=ProxyManager(proxies=list(config.proxy_urls)),
        max_concurrency=config.max_concurrency,
    )
