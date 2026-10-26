"""Typed registry helpers for structured LLM and embedding providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from aha_common_utils.ports.embedding_provider import EmbeddingProviderPort
from aha_common_utils.ports.llm_provider import LLMProviderPort
from aha_common_utils.runtime.provider_registry import (
    UnknownProviderError,
    available_provider_names,
    create_provider_instance,
    register_provider_class,
)


@dataclass(frozen=True, slots=True)
class LLMProviderConfig:
    """Configuration needed to construct a generic LLM provider."""

    provider: str
    base_url: str
    api_key: str
    model: str
    request_timeout_seconds: float = 60.0
    #: 透传给厂商的请求体扩展（关思考等）。None = 不传，保持厂商默认。
    extra_body: dict[str, object] | None = None
    #: 结构化输出实现方式；空 = 适配器默认（function_calling）。
    structured_output_method: str = ""


@dataclass(frozen=True, slots=True)
class EmbeddingProviderConfig:
    """Configuration needed to construct a generic embedding provider."""

    provider: str
    base_url: str
    api_key: str
    model: str
    request_timeout_seconds: float = 60.0


class UnknownLLMProviderError(ValueError):
    """Raised when an LLM provider name has not been registered."""


class UnknownEmbeddingProviderError(ValueError):
    """Raised when an embedding provider name has not been registered."""


def _ensure_builtin_providers() -> None:
    """Import built-in provider modules so their registry decorators run."""
    import aha_common_utils.adapters.openai_compatible_embedding  # noqa: F401
    import aha_common_utils.adapters.openai_compatible_llm  # noqa: F401


def register_llm_provider(name: str, provider_cls: type[LLMProviderPort]) -> type[LLMProviderPort]:
    """Register a non-singleton LLM provider implementation."""
    return register_provider_class(name, provider_cls)


def register_embedding_provider(name: str, provider_cls: type[EmbeddingProviderPort]) -> type[EmbeddingProviderPort]:
    """Register a non-singleton embedding provider implementation."""
    return register_provider_class(name, provider_cls)


def available_llm_providers() -> list[str]:
    """Return registered LLM provider names."""
    _ensure_builtin_providers()
    return list(available_provider_names(LLMProviderPort))

def _optional_provider_kwargs(config: LLMProviderConfig) -> dict[str, object]:
    """只把**显式配置**的可选参数传给 provider 构造器。

    用意：换供应商要能关思考（``extra_body``）和切结构化输出实现（``method``），
    但把这两个键无条件传下去会让不接受它们的替身/第三方 provider 直接 TypeError。
    """
    optional: dict[str, object] = {}
    if config.extra_body:
        optional["extra_body"] = dict(config.extra_body)
    if config.structured_output_method:
        optional["structured_output_method"] = config.structured_output_method
    return optional



def available_embedding_providers() -> list[str]:
    """Return registered embedding provider names."""
    _ensure_builtin_providers()
    return list(available_provider_names(EmbeddingProviderPort))


def create_llm_provider(config: LLMProviderConfig) -> LLMProviderPort:
    """Create an LLM provider from typed config."""
    _ensure_builtin_providers()
    try:
        return cast(
            LLMProviderPort,
            create_provider_instance(
                config.provider,
                LLMProviderPort,
                parameters={
                    "base_url": config.base_url,
                    "api_key": config.api_key,
                    "model": config.model,
                },
                request_timeout_seconds=config.request_timeout_seconds,
                # 仅在显式配置时传，避免给不认识这些参数的 provider/替身加必填 kwargs。
                **_optional_provider_kwargs(config),
            ),
        )
    except UnknownProviderError as exc:
        raise UnknownLLMProviderError(
            f"LLM provider '{config.provider}' not found. Available providers: {', '.join(available_llm_providers())}"
        ) from exc


def create_embedding_provider(config: EmbeddingProviderConfig) -> EmbeddingProviderPort:
    """Create an embedding provider from typed config."""
    _ensure_builtin_providers()
    try:
        return cast(
            EmbeddingProviderPort,
            create_provider_instance(
                config.provider,
                EmbeddingProviderPort,
                parameters={
                    "base_url": config.base_url,
                    "api_key": config.api_key,
                    "model": config.model,
                },
                request_timeout_seconds=config.request_timeout_seconds,
            ),
        )
    except UnknownProviderError as exc:
        raise UnknownEmbeddingProviderError(
            "Embedding provider "
            f"'{config.provider}' not found. Available providers: {', '.join(available_embedding_providers())}"
        ) from exc
