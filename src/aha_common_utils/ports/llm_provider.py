from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

# The canonical rich EmbeddingProviderPort lives in ``embedding_provider``;
# re-exported here for backward compatibility with existing imports.
from aha_common_utils.ports.embedding_provider import EmbeddingProviderPort  # noqa: F401
from aha_common_utils.ports.types import JsonObject, LLMMessage


@dataclass(frozen=True, slots=True)
class ToolCallRequest:
    """一次工具调用（provider 归一后的形态）。"""

    id: str
    name: str
    arguments: JsonObject


@dataclass(frozen=True, slots=True)
class ToolChatResult:
    """带工具调用对话的结果：正文 + 工具调用（可能同时有）。"""

    content: str = ""
    tool_calls: tuple[ToolCallRequest, ...] = ()
    usage: JsonObject = field(default_factory=dict)


class LLMProviderPort(ABC):
    """Structured LLM provider contract."""

    @abstractmethod
    async def complete_json(
        self,
        *,
        messages: list[LLMMessage],
        schema: type[Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> JsonObject:
        """Return a JSON object for supplied chat messages."""

    @abstractmethod
    async def chat(
        self,
        *,
        messages: list[LLMMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        """Return the raw assistant content string for supplied chat messages."""

    async def chat_with_tools(
        self,
        *,
        messages: list[LLMMessage],
        tools: list[dict[str, object]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ToolChatResult:
        """带工具调用的对话（agent 框架需要）。

        默认实现**显式不支持**：任何"静默退化成普通对话"的实现都会让 agent
        以为自己有工具，实际每次工具调用都变成一段文本——这类错配比直接报错难查得多。
        支持工具调用的 provider 必须覆盖本方法。
        """
        raise NotImplementedError(
            f"{type(self).__name__} 未实现 chat_with_tools：agent 框架需要工具调用能力"
        )

    @abstractmethod
    def stream_text(
        self,
        *,
        messages: list[LLMMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Yield text chunks for supplied chat messages."""

    @abstractmethod
    def stream_events(
        self,
        *,
        messages: list[LLMMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        """Yield normalized event dictionaries for supplied chat messages."""

    @abstractmethod
    async def close(self) -> None:
        """Release resources."""
