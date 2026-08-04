"""AutoPlanningEngine — 自适应限流与自动规划引擎。

维护每域速率状态：429/503 触发指数退避，200 缓慢恢复。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass
class RateLimitState:
    """单个域的速率状态。"""

    reflected: bool = False
    consecutive_429: int = 0
    last_429_time: float = 0.0
    current_rate: float = 5.0
    min_rate: float = 0.1
    max_rate: float = 10.0


class AutoPlanningEngine:
    """自适应限流引擎，返回每次请求前的建议延迟（秒）。"""

    def __init__(
        self,
        *,
        initial_rate: float = 5.0,
        min_rate: float = 0.1,
        max_rate: float = 10.0,
        max_backoff_seconds: float = 60.0,
    ) -> None:
        self._state = RateLimitState(current_rate=initial_rate, min_rate=min_rate, max_rate=max_rate)
        self._max_backoff_seconds = max_backoff_seconds
        self._lock = asyncio.Lock()

    async def on_request(self) -> float:
        """返回本次请求前的延迟 = 1/current_rate，封顶 ``max_backoff_seconds``。"""
        async with self._lock:
            return min(1.0 / self._state.current_rate, self._max_backoff_seconds)

    async def on_response(self, status_code: int) -> None:
        """根据响应状态码更新速率状态。"""
        async with self._lock:
            if status_code in (429, 503):
                self._state.consecutive_429 += 1
                self._state.last_429_time = time.time()
                backoff_factor = 2**self._state.consecutive_429
                self._state.current_rate = max(self._state.min_rate, self._state.current_rate / backoff_factor)
            elif status_code == 200:
                self._state.consecutive_429 = 0
                self._state.current_rate = min(self._state.max_rate, self._state.current_rate * 1.1)

    async def get_rate(self) -> float:
        """返回当前速率（req/s）。"""
        async with self._lock:
            return self._state.current_rate
