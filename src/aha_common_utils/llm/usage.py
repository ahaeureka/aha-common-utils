"""Token usage accounting for LLM calls（成本归因，不改变调用语义）。

为什么单独一个模块：成本必须能被"按阶段"归因，而阶段边界在业务代码里（compile / distill /
quality …）。用 ``contextvars`` 记账，调用方只需包一段 ``with record_usage() as ledger``，
provider 侧把每次调用的 usage 追加进去，**不改变任何返回值、不改变失败语义**。

用法::

    from aha_common_utils.llm.usage import record_usage

    with record_usage() as ledger:
        ...  # 任意深度的 LLM 调用
    ledger.as_dict()  # {"calls": 3, "input_tokens": 1234, ...}

未打开 ledger 时，provider 只写 tracing span 属性（零副作用）。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UsageLedger:
    """一次记账区间内的 token 消耗（可变，由 provider 追加）。"""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    #: 未能读到 usage 的调用次数（网关不回 usage 时 > 0——此时成本**不可**按 token 归因）。
    missing_usage_calls: int = 0
    #: 按模型分账：model → 同一组字段。多模型路由时必须区分，否则无法判断哪档在花钱。
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)

    def add(
        self,
        *,
        usage: dict[str, Any] | None,
        model: str,
    ) -> None:
        """记一次调用。``usage`` 为 None / 空 → 只加 ``missing_usage_calls``。"""
        self.calls += 1
        bucket = self.by_model.setdefault(
            model,
            {"calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "missing_usage_calls": 0},
        )
        bucket["calls"] += 1

        input_tokens = _as_int(usage, "input_tokens") if usage else 0
        output_tokens = _as_int(usage, "output_tokens") if usage else 0
        total_tokens = _as_int(usage, "total_tokens") if usage else 0
        if not usage or (input_tokens == 0 and output_tokens == 0 and total_tokens == 0):
            self.missing_usage_calls += 1
            bucket["missing_usage_calls"] += 1
            return

        if not total_tokens:
            total_tokens = input_tokens + output_tokens
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += total_tokens
        bucket["input_tokens"] += input_tokens
        bucket["output_tokens"] += output_tokens
        bucket["total_tokens"] += total_tokens

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "missing_usage_calls": self.missing_usage_calls,
            "by_model": {model: dict(row) for model, row in self.by_model.items()},
        }


_ledger: ContextVar[UsageLedger | None] = ContextVar("k2_llm_usage_ledger", default=None)


@contextmanager
def record_usage() -> Iterator[UsageLedger]:
    """在当前上下文开启记账区间；嵌套调用复用最外层 ledger（避免半截统计）。"""
    existing = _ledger.get()
    if existing is not None:
        yield existing
        return

    ledger = UsageLedger()
    token = _ledger.set(ledger)
    try:
        yield ledger
    finally:
        _ledger.reset(token)


def record_llm_usage(*, usage: dict[str, Any] | None, model: str) -> None:
    """provider 侧调用：有 ledger 才记账，否则静默（调用方未开启记账不是错误）。"""
    ledger = _ledger.get()
    if ledger is not None:
        ledger.add(usage=usage, model=model)


def usage_from_message(message: Any) -> dict[str, Any] | None:
    """从 LangChain ``AIMessage`` 取 usage（兼容 usage_metadata / response_metadata 两种形状）。

    OpenAI 兼容网关常见两种：
    - ``usage_metadata={"input_tokens":..,"output_tokens":..,"total_tokens":..}``
    - ``response_metadata={"token_usage":{"prompt_tokens":..,"completion_tokens":..}}``
    两者都取不到 → 返回 None（由调用方记 missing，而不是当成 0 成本）。
    """
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict) and usage:
        normalized = {
            "input_tokens": _as_int(usage, "input_tokens"),
            "output_tokens": _as_int(usage, "output_tokens"),
            "total_tokens": _as_int(usage, "total_tokens"),
        }
        if any(normalized.values()):
            return normalized

    metadata = getattr(message, "response_metadata", None)
    if isinstance(metadata, dict):
        raw = metadata.get("token_usage") or metadata.get("usage")
        if isinstance(raw, dict) and raw:
            normalized = {
                "input_tokens": _as_int(raw, "prompt_tokens") or _as_int(raw, "input_tokens"),
                "output_tokens": _as_int(raw, "completion_tokens") or _as_int(raw, "output_tokens"),
                "total_tokens": _as_int(raw, "total_tokens"),
            }
            if any(normalized.values()):
                return normalized
    return None


def _as_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


__all__ = [
    "UsageLedger",
    "record_llm_usage",
    "record_usage",
    "usage_from_message",
]
