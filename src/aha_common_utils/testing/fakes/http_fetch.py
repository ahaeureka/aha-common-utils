from __future__ import annotations

from aha_common_utils.ports.http_fetch import (
    AntiCrawlSignal,
    HttpFetchPort,
    HttpFetchRequest,
    HttpFetchResponse,
)
from aha_common_utils.testing.fakes._failure import FailureMixin


class FakeHttpFetchProvider(FailureMixin, HttpFetchPort):
    """Deterministic HTTP fetch provider fake for tests.

    Records every request, serves configured responses (by URL or in FIFO
    order), supports one-shot ``fail_next()`` and ``reset()``.
    """

    def __init__(
        self,
        responses: list[HttpFetchResponse] | None = None,
        *,
        default_status: int = 200,
        default_body: str = "",
    ) -> None:
        super().__init__()
        self._responses = list(responses or [])
        self._url_responses: dict[str, HttpFetchResponse] = {}
        self._default_status = default_status
        self._default_body = default_body
        self.calls: list[HttpFetchRequest] = []

    def add_response(self, response: HttpFetchResponse) -> None:
        """追加一个按 FIFO 顺序返回的响应。"""
        self._responses.append(response)

    def set_response(self, url: str, response: HttpFetchResponse) -> None:
        """为指定 URL 固定返回一个响应。"""
        self._url_responses[url] = response

    async def fetch(self, request: HttpFetchRequest) -> HttpFetchResponse:
        self._raise_if_failed()
        self.calls.append(request)
        if request.url in self._url_responses:
            return self._url_responses[request.url]
        if self._responses:
            return self._responses.pop(0)
        return HttpFetchResponse(status_code=self._default_status, body=self._default_body)

    async def close(self) -> None:
        return None

    def reset(self) -> None:
        self._responses.clear()
        self._url_responses.clear()
        self.calls.clear()
        self._next_failure = None


def make_fetch_response(
    *,
    status_code: int = 200,
    body: str = "",
    strategy_used: str = "fake",
    signal: AntiCrawlSignal = AntiCrawlSignal.NONE,
    proxy_used: str = "",
    attempt_count: int = 1,
    extra: dict[str, object] | None = None,
) -> HttpFetchResponse:
    """Build a minimal HTTP fetch response for tests."""
    return HttpFetchResponse(
        status_code=status_code,
        body=body,
        strategy_used=strategy_used,
        anti_crawl_signal=signal,
        proxy_used=proxy_used,
        attempt_count=attempt_count,
        extra=dict(extra or {}),
    )
