"""Typed helper functions around the shared ProviderRegistry."""

from __future__ import annotations

from typing import Any, TypeVar, cast

from aha_common_utils.register import ClassFactory, ProviderRegistry, register_provider

TProvider = TypeVar("TProvider")


class UnknownProviderError(ValueError):
    """Raised when a provider name is not registered for the requested port."""


def register_provider_class(name: str, provider_cls: type[TProvider]) -> type[TProvider]:
    """Register a non-singleton provider class."""
    return cast("type[TProvider]", register_provider(name, singleton=False)(provider_cls))


def create_provider_instance(
    name: str,
    port_type: type[Any],
    *,
    parameters: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Create a provider instance for a port type."""
    merged = dict(parameters or {})
    merged.update(kwargs)
    try:
        return ClassFactory.get_instance(name, cast(Any, port_type), **merged)
    except ValueError as exc:
        raise UnknownProviderError(f"unknown provider: {name}") from exc


def available_provider_names(port_type: type[Any]) -> tuple[str, ...]:
    """Return sorted provider names registered for a port type."""
    names: list[str] = []
    for name in ProviderRegistry.available_providers():
        provider_cls = ProviderRegistry.get(name)
        if provider_cls is not None and issubclass(provider_cls, port_type):
            names.append(name)
    return tuple(sorted(names))
