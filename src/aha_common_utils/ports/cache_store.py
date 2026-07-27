from __future__ import annotations

from abc import ABC, abstractmethod


class CacheStorePort(ABC):
    """Byte-oriented cache contract."""

    @abstractmethod
    async def get(self, key: str) -> bytes | None:
        """Read a cached value."""

    @abstractmethod
    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        """Write a cached value."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a cached value."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Return whether a cached key exists."""

    @abstractmethod
    async def expire(self, key: str, ttl: int) -> None:
        """Set a TTL for an existing key."""

    @abstractmethod
    async def close(self) -> None:
        """Release resources."""
