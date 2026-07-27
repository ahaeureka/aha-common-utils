"""Typed registry helpers for OCR providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from aha_common_utils.ports.ocr_provider import OcrProviderPort
from aha_common_utils.runtime.provider_registry import (
    UnknownProviderError,
    available_provider_names,
    create_provider_instance,
    register_provider_class,
)


@dataclass(frozen=True, slots=True)
class OcrProviderConfig:
    """Provider creation parameters shared by OCR adapters."""

    provider: str = "remote-ocr"
    api_url: str = ""
    timeout_seconds: float = 60.0
    response_format: str = "verbose"
    extra_params: dict[str, object] = field(default_factory=dict)


class UnknownOcrProviderError(ValueError):
    """Raised when no OCR provider is registered for the requested name."""


def register_ocr_provider(name: str, provider_cls: type[OcrProviderPort]) -> type[OcrProviderPort]:
    """Register a non-singleton OCR provider implementation."""
    return register_provider_class(name, provider_cls)


def available_ocr_providers() -> tuple[str, ...]:
    """Return provider names currently registered for OcrProviderPort."""
    _ensure_builtin_providers()
    return available_provider_names(OcrProviderPort)


def create_ocr_provider(config: OcrProviderConfig) -> OcrProviderPort:
    """Create an OCR provider from typed config."""
    _ensure_builtin_providers()
    kwargs = {
        "api_url": config.api_url,
        "timeout_seconds": config.timeout_seconds,
        "response_format": config.response_format,
        **config.extra_params,
    }
    try:
        return cast(
            OcrProviderPort,
            create_provider_instance(config.provider, OcrProviderPort, parameters=kwargs),
        )
    except UnknownProviderError as exc:
        raise UnknownOcrProviderError(f"unknown OCR provider: {config.provider}") from exc


def register_builtin_ocr_providers() -> None:
    """Register OCR providers shipped by aha-common-utils."""
    from aha_common_utils.adapters.remote_ocr import RemoteOcrClient

    if "remote-ocr" not in available_provider_names(OcrProviderPort):
        register_ocr_provider("remote-ocr", RemoteOcrClient)


def _ensure_builtin_providers() -> None:
    register_builtin_ocr_providers()
