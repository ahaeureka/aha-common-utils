"""Reusable HTTP fetch and anti-detection helpers."""

from aha_common_utils.http_fetch.anti_crawl_detector import AntiCrawlDetector, SiteProfile
from aha_common_utils.http_fetch.anti_detection import (
    DEFAULT_HTTP_HEADERS,
    AntiDetectionManager,
    AntiDetectionStrategy,
    build_default_strategies,
    redact_proxy_url,
)
from aha_common_utils.http_fetch.auto_planning import AutoPlanningEngine, RateLimitState
from aha_common_utils.http_fetch.mitm_ca import MitmCertificateAuthority
from aha_common_utils.http_fetch.provider_registry import (
    HttpFetchProviderConfig,
    UnknownHttpFetchProviderError,
    available_http_fetch_providers,
    create_http_fetch_provider,
    register_builtin_http_fetch_providers,
    register_http_fetch_provider,
)
from aha_common_utils.http_fetch.proxy import Proxy, ProxyManager
from aha_common_utils.http_fetch.proxy_server import CertificateAuthority, HttpProxyServer

__all__ = [
    "AntiCrawlDetector",
    "AntiDetectionManager",
    "AntiDetectionStrategy",
    "AutoPlanningEngine",
    "CertificateAuthority",
    "DEFAULT_HTTP_HEADERS",
    "HttpFetchProviderConfig",
    "HttpProxyServer",
    "MitmCertificateAuthority",
    "Proxy",
    "ProxyManager",
    "RateLimitState",
    "SiteProfile",
    "UnknownHttpFetchProviderError",
    "available_http_fetch_providers",
    "build_default_strategies",
    "create_http_fetch_provider",
    "redact_proxy_url",
    "register_builtin_http_fetch_providers",
    "register_http_fetch_provider",
]
