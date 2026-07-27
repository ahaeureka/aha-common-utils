"""Typed registry helpers for task queue providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from aha_common_utils.ports.task_queue import TaskQueuePort
from aha_common_utils.runtime.provider_registry import (
    UnknownProviderError,
    available_provider_names,
    create_provider_instance,
    register_provider_class,
)


@dataclass(frozen=True, slots=True)
class TaskQueueConfig:
    """Configuration needed to construct a generic task queue."""

    provider: str
    url: str
    stream: str = "tasks"
    group: str = "workers"


class UnknownTaskQueueProviderError(ValueError):
    """Raised when a task queue provider name has not been registered."""


def _ensure_builtin_providers() -> None:
    """Import built-in task queue provider modules so registration is available."""
    from aha_common_utils.adapters.redis_streams_task_queue import RedisStreamsTaskQueue

    if "redis-streams" not in available_provider_names(TaskQueuePort):
        register_task_queue("redis-streams", RedisStreamsTaskQueue)


def register_task_queue(name: str, provider_cls: type[TaskQueuePort]) -> type[TaskQueuePort]:
    """Register a non-singleton task queue provider implementation."""
    return register_provider_class(name, provider_cls)


def available_task_queues() -> list[str]:
    """Return registered task queue provider names."""
    _ensure_builtin_providers()
    return list(available_provider_names(TaskQueuePort))


def create_task_queue(config: TaskQueueConfig) -> TaskQueuePort:
    """Create a task queue from typed config."""
    _ensure_builtin_providers()
    try:
        return cast(
            TaskQueuePort,
            create_provider_instance(
                config.provider,
                TaskQueuePort,
                parameters={
                    "url": config.url,
                    "stream": config.stream,
                    "group": config.group,
                },
            ),
        )
    except UnknownProviderError as exc:
        raise UnknownTaskQueueProviderError(
            f"Task queue provider '{config.provider}' not found. Available providers: {', '.join(available_task_queues())}"
        ) from exc
