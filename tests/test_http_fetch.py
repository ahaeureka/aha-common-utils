"""Tests for the HttpFetch port, anti-detection layer, adapters, registry, and fake.

公共库单测覆盖：检测器各信号分支、策略 ImportError 降级、manager 降级链、
限流退避、代理轮换、provider 注册表与 FakeHttpFetchProvider。
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from aha_common_utils.http_fetch.anti_crawl_detector import AntiCrawlDetector, SiteProfile
from aha_common_utils.http_fetch.anti_detection import (
    AntiDetectionManager,
    AntiDetectionStrategy,
    build_default_strategies,
    redact_proxy_url,
)
from aha_common_utils.http_fetch.auto_planning import AutoPlanningEngine, RateLimitState
from aha_common_utils.http_fetch.provider_registry import (
    HttpFetchProviderConfig,
    UnknownHttpFetchProviderError,
    available_http_fetch_providers,
    create_http_fetch_provider,
)
from aha_common_utils.http_fetch.proxy import Proxy, ProxyManager
from aha_common_utils.ports.http_fetch import (
    AntiCrawlSignal,
    HttpFetchError,
    HttpFetchPort,
    HttpFetchRequest,
    HttpFetchResponse,
)

# ── 端口值对象 ─────────────────────────────────────────────────────


def test_http_fetch_value_objects_are_frozen_dataclasses() -> None:
    request = HttpFetchRequest(url="https://example.com/data", method="GET")
    response = HttpFetchResponse(status_code=200, body="ok")

    assert request.timeout_seconds == 30.0
    assert request.headers == {}
    assert response.strategy_used == ""
    assert response.anti_crawl_signal is AntiCrawlSignal.NONE
    assert response.extra == {}


def test_anti_crawl_signal_enum_values() -> None:
    assert AntiCrawlSignal.STATUS_FORBIDDEN.value == "status_forbidden"
    assert AntiCrawlSignal.STATUS_RATE_LIMITED.value == "status_rate_limited"
    assert AntiCrawlSignal.STATUS_SERVICE_UNAVAILABLE.value == "status_service_unavailable"
    assert AntiCrawlSignal.CAPTCHA_DETECTED.value == "captcha_detected"
    assert AntiCrawlSignal.JS_CHALLENGE.value == "js_challenge"
    assert AntiCrawlSignal.BLOCKED_KEYWORD.value == "blocked_keyword"
    assert AntiCrawlSignal.EMPTY_RESPONSE.value == "empty_response"
    assert AntiCrawlSignal.MINIMAL_RESPONSE.value == "minimal_response"
    assert AntiCrawlSignal.HEADER_CHALLENGE.value == "header_challenge"


# ── 检测器各信号分支 ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (403, AntiCrawlSignal.STATUS_FORBIDDEN),
        (429, AntiCrawlSignal.STATUS_RATE_LIMITED),
        (503, AntiCrawlSignal.STATUS_SERVICE_UNAVAILABLE),
    ],
)
def test_detector_status_code_branches(status_code: int, expected: AntiCrawlSignal) -> None:
    detector = AntiCrawlDetector()
    signal, detail = detector.detect(status_code, "body is long enough to pass length check")
    assert signal is expected
    assert "blocked" in detail


def test_detector_empty_and_minimal_response() -> None:
    detector = AntiCrawlDetector()
    assert detector.detect(200, "   ")[0] is AntiCrawlSignal.EMPTY_RESPONSE
    assert detector.detect(200, "x")[0] is AntiCrawlSignal.MINIMAL_RESPONSE


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("we need you to solve a captcha first", AntiCrawlSignal.CAPTCHA_DETECTED),
        ("正在安全验证，请稍候", AntiCrawlSignal.CAPTCHA_DETECTED),
        ("cf-challenge platform loading", AntiCrawlSignal.JS_CHALLENGE),
        ("checking if your browser is real", AntiCrawlSignal.JS_CHALLENGE),
        ("Access denied by WAF", AntiCrawlSignal.BLOCKED_KEYWORD),
        ("too many requests, rate limit hit", AntiCrawlSignal.BLOCKED_KEYWORD),
        ("请求被拒绝，禁止访问", AntiCrawlSignal.BLOCKED_KEYWORD),
    ],
)
def test_detector_body_regex_branches(body: str, expected: AntiCrawlSignal) -> None:
    signal, _detail = AntiCrawlDetector().detect(200, body * 10)
    assert signal is expected


def test_detector_header_challenge() -> None:
    detector = AntiCrawlDetector()
    signal, detail = detector.detect(
        200,
        "a" * 200,
        headers={"cf-ray": "abcd1234-YYZ", "server": "cloudflare"},
    )
    assert signal is AntiCrawlSignal.HEADER_CHALLENGE
    assert "cf-ray" in detail


def test_detector_normal_response() -> None:
    signal, detail = AntiCrawlDetector().detect(200, "normal content body" * 10, headers={"date": "now"})
    assert signal is AntiCrawlSignal.NONE
    assert detail == ""


def test_detector_custom_site_pattern_takes_precedence() -> None:
    detector = AntiCrawlDetector()
    detector.register_site(
        SiteProfile(
            domain_pattern="example.com",
            custom_patterns=[(AntiCrawlSignal.BLOCKED_KEYWORD, r"site-specific-block", re.IGNORECASE)],
            blocked_status_codes={418},
        )
    )
    assert detector.detect(418, "x" * 200, domain="api.example.com")[0] is AntiCrawlSignal.STATUS_FORBIDDEN
    assert detector.detect(200, "site-specific-block marker" * 5, domain="api.example.com")[0] is (
        AntiCrawlSignal.BLOCKED_KEYWORD
    )


def test_detector_get_site_profile_matches_prefix() -> None:
    detector = AntiCrawlDetector()
    detector.register_site(SiteProfile(domain_pattern="example.com", use_proxy=True))
    profile = detector.get_site_profile("m.example.com")
    assert profile is not None
    assert profile.use_proxy is True
    assert detector.get_site_profile("other.org") is None


def test_detector_is_blocked_shortcut() -> None:
    detector = AntiCrawlDetector()
    assert detector.is_blocked(429, "rate limited body" * 10)
    assert not detector.is_blocked(200, "all good here" * 10)


# ── 策略 ImportError 降级 ──────────────────────────────────────────


class _FakeStrategy(AntiDetectionStrategy):
    def __init__(
        self,
        *,
        result: tuple[int, str, dict[str, Any]] | None = None,
        results: list[tuple[int, str, dict[str, Any]]] | None = None,
        exc: Exception | None = None,
        calls: list[dict[str, Any]] | None = None,
    ) -> None:
        self._result = result
        self._results = list(results) if results else []
        self._exc = exc
        self.calls = calls if calls is not None else []

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
        self.calls.append({"url": url, "method": method, "proxy_url": proxy_url, "strategy": type(self).__name__})
        if self._exc is not None:
            raise self._exc
        if self._results:
            result = self._results.pop(0)
        else:
            result = self._result  # type: ignore[misc]
        status, text, extra = result
        return status, text, dict(extra)


class CurlCffiStrategy(_FakeStrategy):
    pass


class HttpxStrategy(_FakeStrategy):
    pass


class CamoufoxStrategy(_FakeStrategy):
    pass


class BrokenStrategy(_FakeStrategy):
    pass


def _success() -> tuple[int, str, dict[str, Any]]:
    return 200, "hello world content" * 10, {"final_url": "https://example.com/ok", "headers": {}}


def _blocked(status_code: int = 403) -> tuple[int, str, dict[str, Any]]:
    return status_code, "blocked by anti-bot policy" * 5, {"headers": {}}


async def test_manager_skips_strategy_missing_optional_dependency() -> None:
    import_error = BrokenStrategy(exc=ImportError("curl_cffi not installed"))
    fallback = HttpxStrategy(result=_success())
    manager = AntiDetectionManager(strategies=[import_error, fallback])

    response = await manager.fetch(HttpFetchRequest(url="https://example.com/page"))

    assert response.status_code == 200
    assert response.strategy_used == "HttpxStrategy"
    assert response.anti_crawl_signal is AntiCrawlSignal.NONE


async def test_manager_degrades_when_strategy_hits_anti_crawl_signal() -> None:
    blocked = CurlCffiStrategy(result=_blocked(403))
    fallback = HttpxStrategy(result=_success())
    manager = AntiDetectionManager(strategies=[blocked, fallback])

    response = await manager.fetch(HttpFetchRequest(url="https://example.com/page"))

    assert response.status_code == 200
    assert response.strategy_used == "HttpxStrategy"
    assert response.attempt_count == 2


async def test_manager_returns_last_blocked_response_when_all_blocked() -> None:
    blocked_a = CurlCffiStrategy(result=_blocked(403))
    blocked_b = HttpxStrategy(result=_blocked(429))
    manager = AntiDetectionManager(strategies=[blocked_a, blocked_b])

    response = await manager.fetch(HttpFetchRequest(url="https://example.com/page"))

    assert response.anti_crawl_signal is AntiCrawlSignal.STATUS_RATE_LIMITED
    assert response.strategy_used == "HttpxStrategy"


async def test_manager_raises_when_all_strategies_fail() -> None:
    broken = BrokenStrategy(exc=RuntimeError("connection refused"))
    manager = AntiDetectionManager(strategies=[broken])

    with pytest.raises(HttpFetchError, match="all strategies failed"):
        await manager.fetch(HttpFetchRequest(url="https://example.com/page"))


async def test_manager_retries_with_proxy_once_on_anti_crawl_signal() -> None:
    proxy_manager = ProxyManager(proxies=["http://user:pass@proxy.example:8080"])
    strategy = HttpxStrategy(results=[_blocked(429), _success()])
    manager = AntiDetectionManager(strategies=[strategy], proxy_manager=proxy_manager)

    response = await manager.fetch(HttpFetchRequest(url="https://example.com/page"))

    assert response.status_code == 200
    assert response.anti_crawl_signal is AntiCrawlSignal.NONE
    assert response.proxy_used == "http://***@proxy.example:8080"
    assert response.attempt_count == 2
    assert [call["proxy_url"] for call in strategy.calls] == ["", "http://user:pass@proxy.example:8080"]


async def test_manager_forced_proxy_for_restricted_site() -> None:
    proxy_manager = ProxyManager(proxies=["http://user:pass@proxy.example:8080"])
    strategy = HttpxStrategy(result=_success())
    manager = AntiDetectionManager(strategies=[strategy], proxy_manager=proxy_manager)
    manager.register_site(SiteProfile(domain_pattern="example.com", use_proxy=True))

    response = await manager.fetch(HttpFetchRequest(url="https://example.com/page"))

    assert response.status_code == 200
    assert response.proxy_used == "http://***@proxy.example:8080"
    assert strategy.calls[0]["proxy_url"] == "http://user:pass@proxy.example:8080"


async def test_manager_respects_site_strategy_order() -> None:
    first = CamoufoxStrategy(result=_success())
    second = HttpxStrategy(result=_success())
    manager = AntiDetectionManager(strategies=[second, first])
    manager.register_site(
        SiteProfile(domain_pattern="example.com", strategy_order=["CamoufoxStrategy", "HttpxStrategy"])
    )

    response = await manager.fetch(HttpFetchRequest(url="https://example.com/page"))

    assert response.strategy_used == "CamoufoxStrategy"
    assert first.calls[0]["url"] == "https://example.com/page"


def test_redact_proxy_url_hides_credentials() -> None:
    assert redact_proxy_url("") == ""
    assert redact_proxy_url("http://user:secret@proxy.example:8080") == "http://***@proxy.example:8080"
    assert redact_proxy_url("http://proxy.example:8080") == "http://proxy.example:8080"


def test_build_default_strategies_returns_three_strategy_chain_without_httpx() -> None:
    strategies = build_default_strategies()
    names = [type(strategy).__name__ for strategy in strategies]
    assert names == ["CurlCffiStrategy", "CloakBrowserStrategy", "CamoufoxStrategy"]


# ── 自适应限流 ─────────────────────────────────────────────────────


async def test_rate_limit_backoff_on_consecutive_429() -> None:
    engine = AutoPlanningEngine(initial_rate=5.0)
    await engine.on_response(429)
    first_rate = await engine.get_rate()
    await engine.on_response(429)
    second_rate = await engine.get_rate()

    assert first_rate < 5.0
    assert second_rate < first_rate
    assert second_rate >= 0.1


async def test_rate_limit_recovers_on_200() -> None:
    engine = AutoPlanningEngine(initial_rate=0.5)
    await engine.on_response(200)
    await engine.on_response(200)
    recovered = await engine.get_rate()
    assert recovered > 0.5


async def test_rate_limit_state_defaults() -> None:
    state = RateLimitState()
    assert state.current_rate == 5.0
    assert state.min_rate == 0.1
    assert state.max_rate == 10.0


async def test_rate_limit_delay_capped() -> None:
    engine = AutoPlanningEngine(initial_rate=0.01, max_backoff_seconds=3.0)
    delay = await engine.on_request()
    assert delay == 3.0


# ── 代理轮换 ───────────────────────────────────────────────────────


async def test_proxy_manager_get_returns_top_half_by_success_rate() -> None:
    manager = ProxyManager(proxies=["a", "b", "c", "d"])
    await manager.report_success("a")
    await manager.report_success("a")
    await manager.report_failure("a")
    for _ in range(3):
        await manager.report_failure("d")

    chosen = await manager.get_proxy()
    assert chosen in {"a", "b", "c"}


async def test_proxy_manager_marks_dead_after_failures() -> None:
    manager = ProxyManager(proxies=["dead-proxy", "live-proxy"])
    await manager.report_failure("dead-proxy")
    await manager.report_failure("dead-proxy")
    await manager.report_failure("dead-proxy")

    assert [proxy.is_alive for proxy in manager.proxies] == [False, True]
    assert await manager.get_proxy() == "live-proxy"


async def test_proxy_success_rate_property() -> None:
    proxy = Proxy(url="http://p.example")
    assert proxy.success_rate == 1.0
    proxy.fail_count = 3
    proxy.success_count = 1
    assert proxy.success_rate == 0.25


# ── Provider 注册表 ────────────────────────────────────────────────


def test_create_http_fetch_provider_builds_anti_detection_manager() -> None:
    provider = create_http_fetch_provider(HttpFetchProviderConfig())
    assert isinstance(provider, AntiDetectionManager)
    assert isinstance(provider, HttpFetchPort)


def test_default_strategy_chain_starts_with_curl_cffi_and_escalates() -> None:
    provider = create_http_fetch_provider(HttpFetchProviderConfig())
    chain = [type(strategy).__name__ for strategy in provider._strategies]
    assert chain == ["CurlCffiStrategy", "CloakBrowserStrategy", "CamoufoxStrategy"]


def test_create_http_fetch_provider_builds_single_strategy_provider() -> None:
    provider = create_http_fetch_provider(HttpFetchProviderConfig(provider="httpx"))
    assert isinstance(provider, HttpFetchPort)


def test_available_http_fetch_providers_includes_defaults() -> None:
    providers = available_http_fetch_providers()
    assert "anti-detection" in providers
    assert "httpx" in providers
    assert "curl-cffi" in providers


def test_create_http_fetch_provider_unknown_raises() -> None:
    with pytest.raises(UnknownHttpFetchProviderError, match="no-such"):
        create_http_fetch_provider(HttpFetchProviderConfig(provider="no-such"))


# ── FakeHttpFetchProvider ──────────────────────────────────────────


async def test_fake_http_fetch_provider_records_calls_and_serves_by_url() -> None:
    from aha_common_utils.testing.fakes.http_fetch import FakeHttpFetchProvider, make_fetch_response

    provider = FakeHttpFetchProvider()
    provider.set_response(
        "https://example.com/data",
        make_fetch_response(status_code=200, body="payload"),
    )

    response = await provider.fetch(HttpFetchRequest(url="https://example.com/data", domain="example.com"))

    assert response.status_code == 200
    assert response.body == "payload"
    assert provider.calls[0].url == "https://example.com/data"
    assert provider.calls[0].domain == "example.com"


async def test_fake_http_fetch_provider_serves_fifo_responses_and_fails_once() -> None:
    from aha_common_utils.testing.fakes.http_fetch import FakeHttpFetchProvider, make_fetch_response

    provider = FakeHttpFetchProvider(
        responses=[
            make_fetch_response(status_code=429, signal=AntiCrawlSignal.STATUS_RATE_LIMITED),
            make_fetch_response(status_code=200, body="second"),
        ]
    )

    first = await provider.fetch(HttpFetchRequest(url="https://example.com/1"))
    provider.fail_next(ValueError("boom"))
    with pytest.raises(ValueError, match="boom"):
        await provider.fetch(HttpFetchRequest(url="https://example.com/2"))
    second = await provider.fetch(HttpFetchRequest(url="https://example.com/3"))

    assert first.anti_crawl_signal is AntiCrawlSignal.STATUS_RATE_LIMITED
    assert second.body == "second"
    assert len(provider.calls) == 2


async def test_fake_http_fetch_provider_reset_clears_state() -> None:
    from aha_common_utils.testing.fakes.http_fetch import FakeHttpFetchProvider, make_fetch_response

    provider = FakeHttpFetchProvider(default_body="fallback")
    provider.set_response("https://example.com/a", make_fetch_response(body="A"))
    provider.fail_next("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await provider.fetch(HttpFetchRequest(url="https://example.com/a"))

    provider.reset()

    response = await provider.fetch(HttpFetchRequest(url="https://example.com/a"))
    assert response.body == "fallback"
    assert len(provider.calls) == 1


async def test_fake_http_fetch_provider_close_is_idempotent() -> None:
    from aha_common_utils.testing.fakes.http_fetch import FakeHttpFetchProvider

    provider = FakeHttpFetchProvider()
    await provider.close()
    await provider.close()


def test_fake_http_fetch_provider_is_not_importable_in_production_guard() -> None:
    """生产包禁止导入 Fake —— 这里仅验证 fake 落在 testing 命名空间。"""
    from aha_common_utils.testing.fakes.http_fetch import FakeHttpFetchProvider

    assert FakeHttpFetchProvider.__module__.startswith("aha_common_utils.testing")
