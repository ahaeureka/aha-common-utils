"""Typed registry helpers for cache store providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from aha_common_utils.ports.cache_store import CacheStorePort
from aha_common_utils.runtime.provider_registry import (
    UnknownProviderError,
    available_provider_names,
    create_provider_instance,
    register_provider_class,
)


@dataclass(frozen=True, slots=True)
class CacheStoreConfig:
    """Configuration needed to construct a generic cache store."""

    provider: str
    url: str
    key_prefix: str = ""


class UnknownCacheStoreProviderError(ValueError):
    """Raised when a cache store provider name has not been registered."""


def _ensure_builtin_providers() -> None:
    """Import built-in cache provider modules so registration is available."""
    from aha_common_utils.adapters.redis_cache import RedisCacheAdapter

    if "redis-cache" not in available_provider_names(CacheStorePort):
        register_cache_store("redis-cache", RedisCacheAdapter)


def register_cache_store(name: str, provider_cls: type[CacheStorePort]) -> type[CacheStorePort]:
    """Register a non-singleton cache store provider implementation."""
    return register_provider_class(name, provider_cls)


def available_cache_stores() -> list[str]:
    """Return registered cache store provider names."""
    _ensure_builtin_providers()
    return list(available_provider_names(CacheStorePort))


def create_cache_store(config: CacheStoreConfig) -> CacheStorePort:
    """Create a cache store from typed config."""
    _ensure_builtin_providers()
    try:
        return cast(
            CacheStorePort,
            create_provider_instance(
                config.provider,
                CacheStorePort,
                parameters={
                    "url": config.url,
                    "key_prefix": config.key_prefix,
                },
            ),
        )
    except UnknownProviderError as exc:
        raise UnknownCacheStoreProviderError(
            f"Cache store provider '{config.provider}' not found. Available providers: {', '.join(available_cache_stores())}"
        ) from exc
