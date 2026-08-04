"""ProxyManager — 出口代理池管理、健康检查与轮换。"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass

_PROXY_FAIL_RATE_THRESHOLD = 0.2
_PROXY_FAIL_COUNT_THRESHOLD = 3
_HEALTH_CHECK_URL = "http://httpbin.org/ip"


@dataclass
class Proxy:
    """单个出口代理的运行时状态。"""

    url: str
    success_count: int = 0
    fail_count: int = 0
    is_alive: bool = True
    latency_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return self.success_count / total if total > 0 else 1.0


class ProxyManager:
    """代理池管理器，支持轮换、成功率排序与健康检查。"""

    def __init__(self, proxies: list[str] | None = None, health_check_url: str = _HEALTH_CHECK_URL) -> None:
        self._proxies: list[Proxy] = [Proxy(url=url) for url in (proxies or [])]
        self._health_check_url = health_check_url
        self._lock = asyncio.Lock()

    def add_proxy(self, url: str) -> None:
        """新增一个出口代理。"""
        self._proxies.append(Proxy(url=url))

    def remove_proxy(self, url: str) -> None:
        """移除指定出口代理。"""
        self._proxies = [proxy for proxy in self._proxies if proxy.url != url]

    async def get_proxy(self) -> str | None:
        """按成功率降序取前一半随机返回一个存活代理。"""
        async with self._lock:
            alive = [proxy for proxy in self._proxies if proxy.is_alive]
            if not alive:
                return None
            alive.sort(key=lambda proxy: proxy.success_rate, reverse=True)
            candidates = alive[: max(1, len(alive) // 2 + 1)]
            return random.choice(candidates).url

    async def report_success(self, proxy_url: str) -> None:
        """记录一次成功调用。"""
        for proxy in self._proxies:
            if proxy.url == proxy_url:
                proxy.success_count += 1
                break

    async def report_failure(self, proxy_url: str) -> None:
        """记录一次失败调用，成功率过低且失败次数足够时标记不可用。"""
        for proxy in self._proxies:
            if proxy.url == proxy_url:
                proxy.fail_count += 1
                if proxy.success_rate < _PROXY_FAIL_RATE_THRESHOLD and proxy.fail_count >= _PROXY_FAIL_COUNT_THRESHOLD:
                    proxy.is_alive = False
                break

    async def health_check(self, concurrency: int = 3) -> None:
        """并发探测代理存活与延迟。"""
        semaphore = asyncio.Semaphore(concurrency)

        async def _check(proxy: Proxy) -> None:
            async with semaphore:
                try:
                    import httpx

                    start = asyncio.get_event_loop().time()
                    async with httpx.AsyncClient(proxy=proxy.url, timeout=10) as client:
                        response = await client.get(self._health_check_url)
                        proxy.latency_ms = (asyncio.get_event_loop().time() - start) * 1000
                        proxy.is_alive = response.is_success
                except Exception:
                    proxy.is_alive = False

        await asyncio.gather(*[_check(proxy) for proxy in self._proxies], return_exceptions=True)

    @property
    def proxies(self) -> list[Proxy]:
        """当前代理池（只读视图）。"""
        return list(self._proxies)
