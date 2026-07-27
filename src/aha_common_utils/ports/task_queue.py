from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from aha_common_utils.ports.types import JsonObject


class InvalidEnvelopeError(ValueError):
    """Raised when a task envelope cannot be deserialized or is unsupported."""


@dataclass(frozen=True, slots=True)
class TaskContext:
    """Serializable identity and W3C trace context for a queued task."""

    request_id: str
    task_id: str
    traceparent: str = ""
    tracestate: str = ""
    user_id: str | None = None

    def to_dict(self) -> JsonObject:
        payload: JsonObject = {
            "request_id": self.request_id,
            "task_id": self.task_id,
            "traceparent": self.traceparent,
            "tracestate": self.tracestate,
        }
        if self.user_id is not None:
            payload["user_id"] = self.user_id
        return payload

    @classmethod
    def from_dict(cls, data: JsonObject) -> TaskContext:
        request_id = str(data.get("request_id", ""))
        if not request_id:
            raise InvalidEnvelopeError("TaskContext.request_id is required")
        task_id = str(data.get("task_id", "")) or str(uuid.uuid4())
        return cls(
            request_id=request_id,
            task_id=task_id,
            traceparent=str(data.get("traceparent", "")),
            tracestate=str(data.get("tracestate", "")),
            user_id=str(data["user_id"]) if data.get("user_id") else None,
        )


@dataclass(frozen=True, slots=True)
class GenericTaskConfig:
    """Reference-oriented task parameters carried inside a TaskEnvelope."""

    subject_id: str
    subject_version: str = ""
    kind: str = ""
    input_file_id: str = ""
    options: JsonObject = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return {
            "subject_id": self.subject_id,
            "subject_version": self.subject_version,
            "kind": self.kind,
            "input_file_id": self.input_file_id,
            "options": self.options,
        }

    @classmethod
    def from_dict(cls, data: JsonObject) -> GenericTaskConfig:
        if "input_path" in data:
            raise InvalidEnvelopeError("input_path is not allowed in task envelopes")
        raw_options = data.get("options", {})
        if not isinstance(raw_options, dict):
            raise InvalidEnvelopeError("options must be a dict")
        return cls(
            subject_id=str(data.get("subject_id", "")),
            subject_version=str(data.get("subject_version", "")),
            kind=str(data.get("kind", "")),
            input_file_id=str(data.get("input_file_id", "")),
            options=raw_options,
        )


_CURRENT_ENVELOPE_VERSION = 1


@dataclass(frozen=True, slots=True)
class TaskEnvelope:
    """Versioned queue message for asynchronous work."""

    version: int
    task_id: str
    context: TaskContext
    config: GenericTaskConfig
    attempt: int = 1
    metadata: JsonObject = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return {
            "version": self.version,
            "task_id": self.task_id,
            "context": self.context.to_dict(),
            "config": self.config.to_dict(),
            "attempt": self.attempt,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: JsonObject) -> TaskEnvelope:
        raw_version = data.get("version")
        version = int(str(raw_version)) if raw_version is not None else _CURRENT_ENVELOPE_VERSION
        if version != _CURRENT_ENVELOPE_VERSION:
            raise InvalidEnvelopeError(f"Unsupported envelope version {version} (expected {_CURRENT_ENVELOPE_VERSION})")
        raw_context = data.get("context", {})
        if not isinstance(raw_context, dict):
            raise InvalidEnvelopeError("context must be a dict")
        raw_config = data.get("config", {})
        if not isinstance(raw_config, dict):
            raise InvalidEnvelopeError("config must be a dict")
        raw_metadata = data.get("metadata", {})
        if not isinstance(raw_metadata, dict):
            raise InvalidEnvelopeError("metadata must be a dict")
        return cls(
            version=version,
            task_id=str(data.get("task_id", "")),
            context=TaskContext.from_dict(raw_context),
            config=GenericTaskConfig.from_dict(raw_config),
            attempt=int(str(data.get("attempt", 1))),
            metadata=raw_metadata,
        )


class TaskQueuePort(ABC):
    """Abstract async task queue."""

    @abstractmethod
    async def submit(self, envelope: TaskEnvelope) -> None:
        """Submit a task envelope to the queue."""

    @abstractmethod
    async def consume_one(self, consumer_id: str) -> TaskEnvelope | None:
        """Claim and return the next pending task, or None if empty."""

    @abstractmethod
    async def acknowledge(self, task_id: str) -> None:
        """Permanently acknowledge a successfully processed task."""

    @abstractmethod
    async def claim_pending(self, consumer_id: str) -> list[TaskEnvelope]:
        """Recover pending tasks not acknowledged by any consumer."""

    @abstractmethod
    async def close(self) -> None:
        """Release queue resources."""
