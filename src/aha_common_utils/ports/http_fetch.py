"""HttpFetchPort — 统一网络请求与反检测层端口契约。

数据源编译器与爬虫的所有抓取、探测与下载都经该端口，不允许领域代码直接
构造 httpx/curl 客户端。端口值对象用 ``frozen dataclass``（与 OCR/Rerank
端口一致），保持轻量且与公共库现有风格统一。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum

from aha_common_utils.ports.types import JsonObject


class AntiCrawlSignal(StrEnum):
    """反爬信号类型。"""

    NONE = "none"
    STATUS_FORBIDDEN = "status_forbidden"
    STATUS_RATE_LIMITED = "status_rate_limited"
    STATUS_SERVICE_UNAVAILABLE = "status_service_unavailable"
    CAPTCHA_DETECTED = "captcha_detected"
    JS_CHALLENGE = "js_challenge"
    BLOCKED_KEYWORD = "blocked_keyword"
    EMPTY_RESPONSE = "empty_response"
    MINIMAL_RESPONSE = "minimal_response"
    HEADER_CHALLENGE = "header_challenge"


@dataclass(frozen=True, slots=True)
class HttpFetchRequest:
    """一次统一网络请求。"""

    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None
    timeout_seconds: float = 30.0
    domain: str = ""


@dataclass(frozen=True, slots=True)
class HttpFetchResponse:
    """一次统一网络请求的规范化响应。"""

    status_code: int
    body: str
    final_url: str = ""
    strategy_used: str = ""
    anti_crawl_signal: AntiCrawlSignal = AntiCrawlSignal.NONE
    proxy_used: str = ""
    attempt_count: int = 1
    latency_ms: float = 0.0
    extra: JsonObject = field(default_factory=dict)


class HttpFetchPort(ABC):
    """统一网络请求端口契约。"""

    @abstractmethod
    async def fetch(self, request: HttpFetchRequest) -> HttpFetchResponse:
        """发起一次请求并返回规范化响应。"""

    @abstractmethod
    async def close(self) -> None:
        """释放底层资源。"""


class HttpFetchError(RuntimeError):
    """所有策略均失败或全部命中反爬时抛出。"""
