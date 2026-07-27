from __future__ import annotations

import inspect
from typing import Any


class LifecycleRegistry:
    """Register resources that optionally expose initialize() and close()."""

    def __init__(self) -> None:
        self._resources: list[Any] = []

    def register(self, resource: Any) -> None:
        self._resources.append(resource)

    async def initialize_all(self) -> None:
        for resource in self._resources:
            initialize = getattr(resource, "initialize", None)
            if initialize is None:
                continue
            result = initialize()
            if inspect.isawaitable(result):
                await result

    async def close_all(self) -> None:
        seen: set[int] = set()
        for resource in reversed(self._resources):
            await close_once(resource, seen)


async def close_once(resource: Any, seen: set[int]) -> None:
    """Close a resource only once, supporting sync and async close methods."""
    if resource is None:
        return
    resource_id = id(resource)
    if resource_id in seen:
        return
    seen.add(resource_id)
    close = getattr(resource, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result
