"""OpenAI-compatible chat completions adapter backed by LangChain."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from pydantic import SecretStr

from aha_common_utils.llm.json_helpers import coerce_json_object, parse_json_content
from aha_common_utils.ports.llm_provider import LLMProviderPort
from aha_common_utils.ports.types import JsonObject, LLMMessage
from aha_common_utils.register import ProviderRegistry
from aha_common_utils.tracing import get_tracer

_tracer = get_tracer("openai_compatible_llm")


@ProviderRegistry.register("openai-compatible", singleton=False)
class OpenAICompatibleLLMProvider(LLMProviderPort):
    """LLM provider for OpenAI-compatible APIs, using LangChain ChatOpenAI."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        request_timeout_seconds: float = 60.0,
        chat_model: Any = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.request_timeout_seconds = request_timeout_seconds
        self._chat_model: Any = chat_model or self._build_chat_model()

    def _build_chat_model(self) -> Any:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self.model,
            api_key=SecretStr(self.api_key),
            base_url=self.base_url,
            timeout=self.request_timeout_seconds,
        )

    @staticmethod
    def _bind_model_kwargs(runnable: Any, *, temperature: float, max_tokens: int | None) -> Any:
        """Bind per-call generation options when the runnable supports binding."""
        model_kwargs: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            model_kwargs["max_tokens"] = max_tokens

        bind = getattr(runnable, "bind", None)
        return bind(**model_kwargs) if callable(bind) else runnable

    # ── LLMProviderPort ──────────────────────────────────────────────────

    async def complete_json(
        self,
        *,
        messages: list[LLMMessage],
        schema: type[Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> JsonObject:
        lc_messages = _to_langchain_messages(messages)

        with _tracer.start_as_current_span("llm.complete_json") as span:
            span.set_attribute("llm.provider", "openai-compatible")
            span.set_attribute("llm.model", self.model)
            span.set_attribute("llm.message_count", len(messages))
            if schema is not None:
                span.set_attribute("llm.structured_output", schema.__name__)

            try:
                if schema is not None:
                    structured = self._chat_model.with_structured_output(schema)
                    runnable = self._bind_model_kwargs(
                        structured,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                else:
                    runnable = self._bind_model_kwargs(
                        self._chat_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                result = await runnable.ainvoke(lc_messages)
            except Exception as exc:
                span.record_exception(exc)
                raise

        return coerce_json_object(result) if schema is not None else parse_json_content(result)

    async def chat(
        self,
        *,
        messages: list[LLMMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        lc_messages = _to_langchain_messages(messages)

        with _tracer.start_as_current_span("llm.chat") as span:
            span.set_attribute("llm.provider", "openai-compatible")
            span.set_attribute("llm.model", self.model)
            span.set_attribute("llm.message_count", len(messages))

            try:
                runnable = self._bind_model_kwargs(
                    self._chat_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                result = await runnable.ainvoke(lc_messages)
            except Exception as exc:
                span.record_exception(exc)
                raise

        content = getattr(result, "content", None)
        return content if isinstance(content, str) else str(result)

    async def stream_text(
        self,
        *,
        messages: list[LLMMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        lc_messages = _to_langchain_messages(messages)

        with _tracer.start_as_current_span("llm.stream_text") as span:
            span.set_attribute("llm.provider", "openai-compatible")
            span.set_attribute("llm.model", self.model)
            span.set_attribute("llm.message_count", len(messages))
            chunk_count = 0
            try:
                runnable = self._bind_model_kwargs(
                    self._chat_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                async for chunk in runnable.astream(lc_messages):
                    content = getattr(chunk, "content", None)
                    if isinstance(content, str):
                        chunk_count += 1
                        yield content
                span.set_attribute("llm.stream_chunks", chunk_count)
            except Exception as exc:
                span.set_attribute("llm.stream_chunks", chunk_count)
                span.record_exception(exc)
                raise

    async def stream_events(
        self,
        *,
        messages: list[LLMMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        lc_messages = _to_langchain_messages(messages)

        with _tracer.start_as_current_span("llm.stream_events") as span:
            span.set_attribute("llm.provider", "openai-compatible")
            span.set_attribute("llm.model", self.model)
            span.set_attribute("llm.message_count", len(messages))
            event_count = 0
            try:
                runnable = self._bind_model_kwargs(
                    self._chat_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                async for event in runnable.astream_events(lc_messages, version="v2"):
                    event_count += 1
                    yield {
                        "event": event.get("event", ""),
                        "name": event.get("name", ""),
                        "run_id": event.get("run_id", ""),
                        "parent_ids": event.get("parent_ids", []),
                        "tags": event.get("tags", []),
                        "metadata": event.get("metadata", {}),
                        "data": event.get("data", {}),
                    }
                span.set_attribute("llm.stream_events", event_count)
            except Exception as exc:
                span.set_attribute("llm.stream_events", event_count)
                span.record_exception(exc)
                raise

    async def close(self) -> None:
        return None


def _to_langchain_messages(messages: list[LLMMessage]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for msg in messages:
        content = msg.content
        if isinstance(content, list):
            blocks: list[dict[str, object]] = []
            for block in content:
                if hasattr(block, "__dataclass_fields__"):
                    from dataclasses import asdict
                    blocks.append(asdict(block))
                elif isinstance(block, dict):
                    blocks.append(block)
                else:
                    blocks.append({"type": "text", "text": str(block)})
            result.append({"role": msg.role, "content": blocks})
        else:
            result.append({"role": msg.role, "content": content})
    return result
