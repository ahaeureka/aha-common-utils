from __future__ import annotations

import time
import uuid as _uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Literal

from aha_common_utils.ports.types import JsonObject

BillableService = Literal["llm", "embedding", "ocr"]


@dataclass(slots=True)
class BillableSpan:
    """Single billable adapter call recorded against a request."""

    service: BillableService
    model: str
    input_units: int
    output_units: int
    latency_ms: float
    trace_id: str
    error: str | None = None


@dataclass(slots=True)
class RequestContext:
    """Request-level context propagated with contextvars."""

    request_id: str
    user_id: str = ""
    task_id: str | None = None
    started_at: float = field(default_factory=time.time)
    session_id: str | None = None
    metadata: JsonObject = field(default_factory=dict)
    billable_spans: list[BillableSpan] = field(default_factory=list)

    def record_span(self, span: BillableSpan) -> None:
        self.billable_spans.append(span)

    @property
    def total_llm_input_tokens(self) -> int:
        return sum(span.input_units for span in self.billable_spans if span.service == "llm")

    @property
    def total_llm_output_tokens(self) -> int:
        return sum(span.output_units for span in self.billable_spans if span.service == "llm")

    @property
    def billable_spans_count(self) -> int:
        return len(self.billable_spans)


_request_ctx: ContextVar[RequestContext | None] = ContextVar("aha_common_request_ctx", default=None)


def ensure_request_id(request_id: str = "") -> str:
    """Return the supplied request id or generate a UUID when absent."""
    return request_id if request_id else str(_uuid.uuid4())


def _set_logging_request_id(request_id: str) -> Token[str] | None:
    try:
        from aha_common_utils.log import request_id_var

        return request_id_var.set(request_id)
    except Exception:
        return None


def get_request_context() -> RequestContext | None:
    return _request_ctx.get()


def set_request_context(ctx: RequestContext) -> tuple[Token[RequestContext | None], Token[str] | None]:
    log_token = _set_logging_request_id(ctx.request_id)
    ctx_token = _request_ctx.set(ctx)
    return ctx_token, log_token


def reset_request_context(
    ctx_token: Token[RequestContext | None],
    log_token: Token[str] | None = None,
) -> None:
    _request_ctx.reset(ctx_token)
    if log_token is not None:
        try:
            from aha_common_utils.log import request_id_var

            request_id_var.reset(log_token)
        except Exception:
            pass


@contextmanager
def request_context(ctx: RequestContext) -> Iterator[RequestContext]:
    ctx_token, log_token = set_request_context(ctx)
    try:
        yield ctx
    finally:
        reset_request_context(ctx_token, log_token)
