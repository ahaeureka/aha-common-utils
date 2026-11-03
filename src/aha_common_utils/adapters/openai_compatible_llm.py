"""OpenAI-compatible chat completions adapter backed by LangChain."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, SecretStr, create_model

from aha_common_utils.llm.json_helpers import coerce_json_object, parse_json_content
from aha_common_utils.llm.usage import record_llm_usage, usage_from_message
from aha_common_utils.ports.llm_provider import (
    LLMProviderPort,
    ToolCallRequest,
    ToolChatResult,
)
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
        extra_body: dict[str, object] | None = None,
        structured_output_method: str = "",
        chat_model: Any = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.request_timeout_seconds = request_timeout_seconds
        self.extra_body: dict[str, object] = dict(extra_body or {})
        self.structured_output_method = structured_output_method
        self._chat_model: Any = chat_model or self._build_chat_model()

    async def chat_with_tools(
        self,
        *,
        messages: list[LLMMessage],
        tools: list[dict[str, object]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ToolChatResult:
        """带工具调用：把 OpenAI 兼容的工具 schema 交给底层 chat model。

        `tools` 用 **OpenAI function 形态**（`{"type":"function","function":{...}}`），
        由调用方的 langchain 适配层转换——本层不引入 langchain 类型，
        否则端口会反向依赖框架。
        """
        bound = self._chat_model.bind_tools(tools) if tools else self._chat_model
        bound = self._bind_model_kwargs(bound, temperature=temperature, max_tokens=max_tokens)
        raw = await bound.ainvoke([self._to_langchain(msg) for msg in messages])
        content = raw.content if isinstance(raw.content, str) else str(raw.content or "")
        calls: list[ToolCallRequest] = []
        for item in getattr(raw, "tool_calls", None) or ():
            if isinstance(item, dict):
                name = str(item.get("name") or "")
                args = item.get("args") or {}
                call_id = str(item.get("id") or f"call_{len(calls)}")
            else:  # pragma: no cover - langchain 也可能给 TypedDict/对象
                name = str(getattr(item, "name", ""))
                args = getattr(item, "args", {}) or {}
                call_id = str(getattr(item, "id", f"call_{len(calls)}"))
            if name:
                calls.append(
                    ToolCallRequest(id=call_id, name=name, arguments=dict(args))
                )
        usage = dict(getattr(raw, "usage_metadata", None) or {})
        return ToolChatResult(content=content, tool_calls=tuple(calls), usage=usage)

    @staticmethod
    def _to_langchain(message: LLMMessage) -> Any:
        """端口消息 → langchain 消息（只做形态转换，不做内容改写）。"""
        from langchain_core.messages import (
            AIMessage,
            HumanMessage,
            SystemMessage,
            ToolMessage,
        )

        role = str(getattr(message, "role", "user"))
        content = getattr(message, "content", "")
        text = content if isinstance(content, str) else str(content)
        if role == "system":
            return SystemMessage(content=text)
        if role == "assistant":
            calls = tuple(getattr(message, "tool_calls", ()) or ())
            return AIMessage(content=text, tool_calls=[dict(call) for call in calls])
        if role == "tool":
            tool_call_id = str(getattr(message, "tool_call_id", "") or "")
            return ToolMessage(content=text, tool_call_id=tool_call_id)
        return HumanMessage(content=text)

    @property
    def chat_model(self) -> Any:
        """暴露内部持有的 LangChain chat model（供 agent 框架注入使用）。

        为什么需要公开取用器：Deep Agents / LangGraph 的 agent 节点需要**langchain
        的 chat model**，而本端口内部已经持有一份。没有取用器时，调用方只能按
        `base_url`/`api_key`/`model`/`extra_body` 再建一份——两份构造会在换模型、
        改超时、加厂商参数时静默错配（端口换了、agent 没换）。

        返回的是**同一个对象**（不是副本）：改它的配置会同时影响端口与 agent，
        这正是"单一构造点"的语义。
        """
        return self._chat_model

    def _build_chat_model(self) -> Any:
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": self.model,
            "api_key": SecretStr(self.api_key),
            "base_url": self.base_url,
            "timeout": self.request_timeout_seconds,
        }
        if self.extra_body:
            # 厂商私有参数（关思考等）只能经 extra_body 透传，ChatOpenAI 不接受裸键。
            kwargs["extra_body"] = dict(self.extra_body)
        return ChatOpenAI(**kwargs)

    @staticmethod
    def _bind_model_kwargs(runnable: Any, *, temperature: float, max_tokens: int | None) -> Any:
        """Bind per-call generation options when the runnable supports binding."""
        model_kwargs: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            model_kwargs["max_tokens"] = max_tokens

        bind = getattr(runnable, "bind", None)
        return bind(**model_kwargs) if callable(bind) else runnable

    def _structured_runnable(self, schema: type[Any]) -> tuple[Any, bool]:
        """Build the structured runnable without silently changing the selected protocol."""
        # Some OpenAI-compatible endpoints escape a leading underscore in a tool
        # name. Give private Pydantic models a public wire name while inheriting
        # their fields and validators; never mutate the caller's schema.
        tool_schema = schema
        if isinstance(schema, type) and issubclass(schema, BaseModel) and schema.__name__.startswith("_"):
            tool_name = schema.__name__.lstrip("_")
            if not tool_name:
                raise ValueError("structured output schema has no public tool name")
            tool_schema = create_model(tool_name, __base__=schema, __module__=schema.__module__)

        kwargs: dict[str, Any] = {"include_raw": True}
        if self.structured_output_method:
            kwargs["method"] = self.structured_output_method
            # An explicit method is a wire contract, not a hint: don't retry
            # without it when a model does not accept these options.
            return self._chat_model.with_structured_output(tool_schema, **kwargs), True
        try:
            return self._chat_model.with_structured_output(tool_schema, **kwargs), True
        except TypeError:
            # Backward compatibility for test doubles / legacy model wrappers.
            return self._chat_model.with_structured_output(tool_schema), False

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
                    structured, include_raw = self._structured_runnable(schema)
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
                # usage 必须在 span 仍打开时读取：结构化输出把真身包在 ``raw`` 里。
                usage_source = (
                    result.get("raw")
                    if (schema is not None and include_raw and isinstance(result, dict))
                    else result
                )
                _apply_usage(usage_source, span=span, model=self.model)
            except Exception as exc:
                span.record_exception(exc)
                raise

        if schema is None:
            return parse_json_content(result)

        if include_raw:
            raw = result.get("raw") if isinstance(result, dict) else None
            parsed = result.get("parsed") if isinstance(result, dict) else None
            error = result.get("parsing_error") if isinstance(result, dict) else None
            if error is not None:
                # 保持既有失败语义：结构化解析失败必须抛出，不得返回半截对象。
                raise ValueError(f"LLM structured response could not be parsed: {error}") from error
            return coerce_json_object(parsed if parsed is not None else raw)

        return coerce_json_object(result)

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
                _apply_usage(result, span=span, model=self.model)
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


def _apply_usage(message: Any, *, span: Any, model: str) -> None:
    """把一次调用的 usage 同时写到 tracing span 与（若已开启的）记账 ledger。

    读不到 usage 时**不猜**：span 标 ``llm.usage_missing=true``，ledger 记
    ``missing_usage_calls``——否则 0 成本会伪造出"免费"的结论。
    """
    usage = usage_from_message(message)
    if usage is None:
        span.set_attribute("llm.usage_missing", True)
        record_llm_usage(usage=None, model=model)
        return
    span.set_attribute("llm.input_tokens", usage["input_tokens"])
    span.set_attribute("llm.output_tokens", usage["output_tokens"])
    span.set_attribute("llm.total_tokens", usage["total_tokens"])
    record_llm_usage(usage=usage, model=model)


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
