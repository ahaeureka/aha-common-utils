"""换供应商所需的参数通道（关思考 / 结构化输出方式 / 超时）。

这三项不写测试就会静默失效：配置里看着有值，实际没透传到 ChatOpenAI，
结果就是"以为关了思考、实际每候选多花 3 倍 token"，或"以为换了 json_schema、实际还在走 function calling"。
"""

from __future__ import annotations

import pytest
from aha_common_utils.adapters.openai_compatible_llm import OpenAICompatibleLLMProvider
from aha_common_utils.ports.types import LLMMessage


def test_extra_body_is_forwarded_to_chat_model() -> None:
    """DeepSeek 默认思考开启；关思考只能靠 extra_body，丢了就等于没关。"""
    provider = OpenAICompatibleLLMProvider(
        base_url="http://gateway.invalid/v1",
        api_key="k",
        model="deepseek-flash",
        extra_body={"thinking": {"type": "disabled"}},
    )

    assert provider._chat_model.extra_body == {"thinking": {"type": "disabled"}}


def test_extra_body_absent_means_vendor_default() -> None:
    """默认必须为空：多数网关不认识 ``thinking``/``enable_thinking`` 会直接 400。"""
    provider = OpenAICompatibleLLMProvider(
        base_url="http://gateway.invalid/v1",
        api_key="k",
        model="some-model",
    )

    assert getattr(provider._chat_model, "extra_body", None) in (None, {})


def test_request_timeout_is_configurable_not_hardcoded() -> None:
    """思考型模型与长 draft 会超过 60s；超时后会被富化 fail-open 吞成"字段为空"。"""
    provider = OpenAICompatibleLLMProvider(
        base_url="http://gateway.invalid/v1",
        api_key="k",
        model="m",
        request_timeout_seconds=120.0,
    )

    assert provider.request_timeout_seconds == 120.0
    assert provider._chat_model.request_timeout == 120.0


class _MethodRecordingModel:
    def __init__(self) -> None:
        self.seen: dict[str, object] = {}

    def with_structured_output(self, schema: object, **kwargs: object):  # noqa: ANN001, ANN201
        self.seen = dict(kwargs)

        class _Runnable:
            def bind(self, **bound: object):  # noqa: ANN003, ANN201
                return self

            async def ainvoke(self, messages: object):  # noqa: ANN001, ANN201
                return {"raw": None, "parsed": {"ok": True}, "parsing_error": None}

        return _Runnable()


@pytest.mark.asyncio
async def test_structured_output_method_is_applied_when_configured() -> None:
    """自建 vLLM 要用 json_schema（guided decoding），否则 32B 的 schema 合法率不可控。"""
    model = _MethodRecordingModel()
    provider = OpenAICompatibleLLMProvider(
        base_url="http://gateway.invalid/v1",
        api_key="k",
        model="m",
        chat_model=model,
        structured_output_method="json_schema",
    )

    await provider.complete_json(messages=[LLMMessage(role="user", content="hi")], schema=dict)

    assert model.seen.get("method") == "json_schema"
    assert model.seen.get("include_raw") is True


@pytest.mark.asyncio
async def test_structured_output_method_absent_keeps_langchain_default() -> None:
    model = _MethodRecordingModel()
    provider = OpenAICompatibleLLMProvider(
        base_url="http://gateway.invalid/v1",
        api_key="k",
        model="m",
        chat_model=model,
    )

    await provider.complete_json(messages=[LLMMessage(role="user", content="hi")], schema=dict)

    assert "method" not in model.seen, "未配置时不得改变 LangChain 默认（版本相关，须在目标端点验证）"
