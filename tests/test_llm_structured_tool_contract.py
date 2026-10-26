"""Offline contract tests for OpenAI-compatible structured tool calls."""

from __future__ import annotations

import json

import httpx
import pytest
from aha_common_utils.adapters.openai_compatible_llm import OpenAICompatibleLLMProvider
from aha_common_utils.llm.usage import record_usage
from aha_common_utils.ports.types import LLMMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, field_validator


class _PrivatePayload(BaseModel):
    name: str
    triggers: list[str]

    @field_validator("triggers")
    @classmethod
    def require_trigger(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("trigger required")
        return value


@pytest.mark.asyncio
@pytest.mark.parametrize("triggers", [["x"], []])
async def test_private_schema_uses_public_tool_name_without_weakening_validation(triggers: list[str]) -> None:
    """A provider that escapes leading underscores must still return validated fields and usage."""
    seen: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen.append(payload)
        tool_name = payload["tools"][0]["function"]["name"]
        # Characterize the observed DeepSeek response: a private tool name came
        # back escaped, which LangChain could not match to the registered tool.
        response_name = f"\\{tool_name}" if tool_name.startswith("_") else tool_name
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-local",
                "object": "chat.completion",
                "created": 1,
                "model": "deepseek-flash",
                "choices": [{
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call-local",
                            "type": "function",
                            "function": {"name": response_name, "arguments": json.dumps({"name": "method", "triggers": triggers})},
                        }],
                    },
                }],
                "usage": {"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        chat = ChatOpenAI(
            model="deepseek-flash",
            api_key="test-only",
            base_url="https://api.example.test",
            http_async_client=client,
            max_retries=0,
        )
        provider = OpenAICompatibleLLMProvider(
            base_url="https://api.example.test",
            api_key="test-only",
            model="deepseek-flash",
            structured_output_method="function_calling",
            chat_model=chat,
        )
        with record_usage() as ledger:
            if triggers:
                result = await provider.complete_json(
                    messages=[LLMMessage(role="user", content="extract a method")],
                    schema=_PrivatePayload,
                )
                assert result["name"] == "method"
                assert result["triggers"] == triggers
            else:
                with pytest.raises(ValueError, match="trigger required"):
                    await provider.complete_json(
                        messages=[LLMMessage(role="user", content="extract a method")],
                        schema=_PrivatePayload,
                    )
    assert seen[0]["tools"][0]["function"]["name"] == "PrivatePayload"
    assert "response_format" not in seen[0]
    assert ledger.as_dict()["total_tokens"] == 13


@pytest.mark.asyncio
async def test_explicit_structured_method_cannot_silently_fall_back() -> None:
    """An unsupported explicit method must fail, rather than changing wire protocol."""

    class LegacyModel:
        def with_structured_output(self, schema: object):  # noqa: ANN001, ANN201
            raise AssertionError("explicit method was silently discarded")

    provider = OpenAICompatibleLLMProvider(
        base_url="https://api.example.test",
        api_key="test-only",
        model="deepseek-flash",
        structured_output_method="function_calling",
        chat_model=LegacyModel(),
    )
    with pytest.raises(TypeError, match="method"):
        await provider.complete_json(
            messages=[LLMMessage(role="user", content="extract a method")],
            schema=_PrivatePayload,
        )


def test_json_schema_mapping_is_forwarded_without_pydantic_aliasing() -> None:
    """A shared provider must not reject JSON-schema mappings accepted by LangChain."""
    seen: list[object] = []

    class Model:
        def with_structured_output(self, schema: object, **kwargs: object) -> object:
            seen.append(schema)
            return object()

    provider = OpenAICompatibleLLMProvider(
        base_url="https://api.example.test",
        api_key="test-only",
        model="deepseek-flash",
        structured_output_method="function_calling",
        chat_model=Model(),
    )
    schema = {"title": "Payload", "type": "object", "properties": {"name": {"type": "string"}}}
    provider._structured_runnable(schema)
    assert seen == [schema]
