"""LLM token 记账（成本归因）的不变量。

为什么单独成文件：成本口径一旦**猜测**就会伪造结论。这里锁三件事：
1. 读不到 usage 时必须记 ``missing_usage_calls``，不能当 0；
2. 嵌套记账复用最外层 ledger，避免同一批调用被统计两次；
3. provider 在结构化输出路径上仍能取到 usage（走 ``include_raw`` 的 ``raw``）。
"""

from __future__ import annotations

import pytest
from aha_common_utils.adapters.openai_compatible_llm import OpenAICompatibleLLMProvider
from aha_common_utils.llm.usage import (
    record_usage,
    usage_from_message,
)
from aha_common_utils.ports.types import LLMMessage
from langchain_core.messages import AIMessage


def test_usage_from_message_prefers_usage_metadata() -> None:
    msg = AIMessage(
        content="ok",
        usage_metadata={"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
    )
    assert usage_from_message(msg) == {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}


def test_usage_from_message_falls_back_to_response_metadata_token_usage() -> None:
    """网关常只给 OpenAI 原生字段（prompt/completion）；不得因此记成 0 成本。"""
    msg = AIMessage(
        content="ok",
        response_metadata={"token_usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}},
    )
    assert usage_from_message(msg) == {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8}


def test_usage_from_message_returns_none_when_absent() -> None:
    assert usage_from_message(AIMessage(content="ok")) is None


def test_ledger_sums_calls_and_models() -> None:
    with record_usage() as ledger:
        from aha_common_utils.llm.usage import record_llm_usage

        record_llm_usage(usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}, model="m-a")
        record_llm_usage(usage={"input_tokens": 4, "output_tokens": 1, "total_tokens": 5}, model="m-b")
        record_llm_usage(usage=None, model="m-b")

    snapshot = ledger.as_dict()
    assert snapshot["calls"] == 3
    assert snapshot["input_tokens"] == 14
    assert snapshot["output_tokens"] == 3
    assert snapshot["total_tokens"] == 17
    assert snapshot["missing_usage_calls"] == 1, "读不到 usage 必须单独计数，不能当 0 成本"
    assert set(snapshot["by_model"]) == {"m-a", "m-b"}
    assert snapshot["by_model"]["m-b"]["missing_usage_calls"] == 1


def test_nested_record_usage_reuses_outer_ledger() -> None:
    """嵌套区间必须并入最外层：否则内层会开新账，统计出半截成本。"""
    with record_usage() as outer:
        from aha_common_utils.llm.usage import record_llm_usage

        record_llm_usage(usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}, model="m")
        with record_usage() as inner:
            assert inner is outer
            record_llm_usage(usage={"input_tokens": 2, "output_tokens": 2, "total_tokens": 4}, model="m")

    assert outer.as_dict()["calls"] == 2
    assert outer.as_dict()["total_tokens"] == 6


def test_ledger_absent_is_silent_noop() -> None:
    """未开启记账时不得抛错，也不得保留全局状态。"""
    from aha_common_utils.llm.usage import record_llm_usage

    record_llm_usage(usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}, model="m")
    with record_usage() as ledger:
        pass
    assert ledger.as_dict()["calls"] == 0


class _FakeStructuredModel:
    """按 LangChain 形状返回 ``{raw, parsed, parsing_error}`` 的替身。"""

    def __init__(self, *, usage: dict[str, int] | None) -> None:
        self._usage = usage
        self.include_raw_seen: bool | None = None

    def with_structured_output(self, schema: object, *, include_raw: bool = False):  # noqa: ANN001, ANN201
        self.include_raw_seen = include_raw

        class _Runnable:
            def __init__(self, usage: dict[str, int] | None) -> None:
                self._usage = usage

            def bind(self, **kwargs: object):  # noqa: ANN201, ANN003
                return self

            async def ainvoke(self, messages: object):  # noqa: ANN001, ANN201
                raw = (
                    AIMessage(content='{"name": "x"}', usage_metadata=self._usage)
                    if self._usage
                    else AIMessage(content='{"name": "x"}')
                )
                return {"raw": raw, "parsed": {"name": "x"}, "parsing_error": None}

        return _Runnable(self._usage)


@pytest.mark.asyncio
async def test_provider_records_usage_for_structured_output() -> None:
    """结构化输出把结果包在 raw 里；usage 必须从 raw 读到，否则成本永远是 0。"""
    model = _FakeStructuredModel(usage={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150})
    provider = OpenAICompatibleLLMProvider(
        base_url="http://gateway.invalid/v1",
        api_key="k",
        model="m-test",
        chat_model=model,
    )

    with record_usage() as ledger:
        payload = await provider.complete_json(
            messages=[LLMMessage(role="user", content="hi")],
            schema=dict,
        )

    assert payload == {"name": "x"}, "结构化输出必须返回解析后的对象，而不是 raw 包装"
    assert model.include_raw_seen is True, "必须请求 raw，否则拿不到 usage"
    snapshot = ledger.as_dict()
    assert snapshot["input_tokens"] == 120
    assert snapshot["output_tokens"] == 30
    assert snapshot["missing_usage_calls"] == 0
    assert snapshot["by_model"]["m-test"]["total_tokens"] == 150


@pytest.mark.asyncio
async def test_provider_marks_missing_usage_instead_of_free() -> None:
    """网关不回 usage 时记 missing，而不是结算成 0 token。"""
    model = _FakeStructuredModel(usage=None)
    provider = OpenAICompatibleLLMProvider(
        base_url="http://gateway.invalid/v1",
        api_key="k",
        model="m-test",
        chat_model=model,
    )

    with record_usage() as ledger:
        await provider.complete_json(messages=[LLMMessage(role="user", content="hi")], schema=dict)

    snapshot = ledger.as_dict()
    assert snapshot["calls"] == 1
    assert snapshot["total_tokens"] == 0
    assert snapshot["missing_usage_calls"] == 1
