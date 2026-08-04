"""Typed registry helpers for rerank providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from aha_common_utils.ports.rerank_provider import RerankProviderPort
from aha_common_utils.runtime.provider_registry import (
    UnknownProviderError,
    available_provider_names,
    create_provider_instance,
    register_provider_class,
)


@dataclass(frozen=True, slots=True)
class RerankProviderConfig:
    """Configuration needed to construct a generic rerank provider."""

    provider: str
    api_url: str = ""
    api_key: str = ""
    model: str = ""
    model_path: str = ""
    request_timeout_seconds: float = 60.0


class UnknownRerankProviderError(ValueError):
    """Raised when a rerank provider name has not been registered."""


def _ensure_builtin_providers() -> None:
    """Import built-in rerank provider modules so registration is available."""
    from aha_common_utils.adapters.llama_cpp_rerank import LlamaCppRerankProvider
    from aha_common_utils.adapters.remote_openai_rerank import RemoteOpenAIRerankProvider

    registered: set[str] = set(available_provider_names(RerankProviderPort))
    if "remote-openai-rerank" not in registered:
        register_rerank_provider("remote-openai-rerank", RemoteOpenAIRerankProvider)
    if "llama-cpp-rerank" not in registered:
        register_rerank_provider("llama-cpp-rerank", LlamaCppRerankProvider)


def register_rerank_provider(name: str, provider_cls: type[RerankProviderPort]) -> type[RerankProviderPort]:
    """Register a non-singleton rerank provider implementation."""
    return register_provider_class(name, provider_cls)


def available_rerank_providers() -> list[str]:
    """Return registered rerank provider names."""
    _ensure_builtin_providers()
    return list(available_provider_names(RerankProviderPort))


def create_rerank_provider(config: RerankProviderConfig) -> RerankProviderPort:
    """Create a rerank provider from typed config.

    Args:
        config: Provider selection and connection parameters.

    Returns:
        A :class:`RerankProviderPort` instance.

    Raises:
        UnknownRerankProviderError: If the provider name is not registered.
    """
    _ensure_builtin_providers()
    try:
        return cast(
            RerankProviderPort,
            create_provider_instance(
                config.provider,
                RerankProviderPort,
                parameters={
                    "api_url": config.api_url,
                    "api_key": config.api_key,
                    "model": config.model,
                    "model_path": config.model_path,
                    "request_timeout_seconds": config.request_timeout_seconds,
                },
            ),
        )
    except UnknownProviderError as exc:
        raise UnknownRerankProviderError(
            "Rerank provider "
            f"'{config.provider}' not found. Available providers: {', '.join(available_rerank_providers())}"
        ) from exc
