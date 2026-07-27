from __future__ import annotations

from typing import Any

from aha_common_utils.ports.cache_store import CacheStorePort


class RedisCacheAdapter(CacheStorePort):
    """Redis-backed byte cache adapter."""

    def __init__(self, url: str, key_prefix: str = "") -> None:
        self._url = url
        self._key_prefix = key_prefix.strip(":")
        self._client: Any | None = None

    @property
    def _redis(self) -> Any | None:
        """Backward-compatible alias for the underlying Redis client."""
        return self._client

    def _ensure_connected(self) -> Any:
        """Create the Redis client on first use."""
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(self._url)
        return self._client

    def _key(self, key: str) -> str:
        if not key or not key.strip():
            raise ValueError("key must not be empty")
        if not self._key_prefix:
            return key
        prefix = f"{self._key_prefix}:"
        if key.startswith(prefix):
            raise ValueError(f"key already has prefix: {key}")
        return f"{prefix}{key}"

    async def get(self, key: str) -> bytes | None:
        client = self._ensure_connected()
        value = await client.get(self._key(key))
        return value if isinstance(value, bytes) or value is None else bytes(value)

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        client = self._ensure_connected()
        await client.set(self._key(key), value, ex=ttl)

    async def delete(self, key: str) -> None:
        client = self._ensure_connected()
        await client.delete(self._key(key))

    async def exists(self, key: str) -> bool:
        client = self._ensure_connected()
        return bool(await client.exists(self._key(key)))

    async def expire(self, key: str, ttl: int) -> None:
        client = self._ensure_connected()
        await client.expire(self._key(key), ttl)

    async def close(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.aclose()
        finally:
            self._client = None
