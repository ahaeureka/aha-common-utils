"""Shared DTOs for business-independent ports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

JsonObject = dict[str, object]
EmbeddingVector = list[float]
LLMRole = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class StoredFileInfo:
    file_id: str
    filename: str
    content_type: str
    size_bytes: int
    metadata: JsonObject = field(default_factory=dict)
    content_sha256: str = ""


@dataclass(frozen=True, slots=True)
class TextContent:
    type: str = "text"
    text: str = ""


@dataclass(frozen=True, slots=True)
class ImageUrlContent:
    type: str = "image_url"
    url: str = ""
    detail: Literal["auto", "low", "high"] = "auto"


ContentBlock = TextContent | ImageUrlContent
LLMContent = str | list[ContentBlock]


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: LLMRole
    content: LLMContent
    #: 工具结果对应的调用 id（role="tool" 时必填；否则上游会拒绝）
    tool_call_id: str | None = None
    #: assistant 轮次里的工具调用（回放历史时必须原样带回，否则 OpenAI 会拒"孤立 tool 消息"）
    tool_calls: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class GraphNode:
    id: str
    labels: tuple[str, ...]
    properties: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GraphEdge:
    from_id: str
    to_id: str
    rel_type: str
    properties: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GraphTraversal:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
