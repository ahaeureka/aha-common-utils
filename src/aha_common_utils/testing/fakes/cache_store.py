from __future__ import annotations

from aha_common_utils.ports.cache_store import CacheStorePort
from aha_common_utils.testing.fakes._failure import FailureMixin


class FakeCacheStore(FailureMixin, CacheStorePort):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def reset(self) -> None:
        self.values.clear()
        self.ttls.clear()
        self._next_failure = None

    async def get(self, key: str) -> bytes | None:
        self._raise_if_failed()
        return self.values.get(key)

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        self._raise_if_failed()
        self.values[key] = value
        if ttl is not None:
            self.ttls[key] = ttl

    async def delete(self, key: str) -> None:
        self._raise_if_failed()
        self.values.pop(key, None)
        self.ttls.pop(key, None)

    async def exists(self, key: str) -> bool:
        self._raise_if_failed()
        return key in self.values

    async def expire(self, key: str, ttl: int) -> None:
        self._raise_if_failed()
        if key in self.values:
            self.ttls[key] = ttl

    async def close(self) -> None:
        return None
