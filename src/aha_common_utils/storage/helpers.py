"""Reusable helpers for file storage adapters."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

TSecurityError = TypeVar("TSecurityError", bound=Exception)


def sanitize_path_part(value: str) -> str:
    """Return a conservative path component for object storage keys."""
    value = value.strip().strip("/")
    return re.sub(r"[^A-Za-z0-9._/-]+", "-", value).strip("-")


def sanitize_metadata_key(value: str) -> str:
    """Return a conservative metadata key."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value.lower()).strip("-") or "metadata"


async def enforce_clean_scan(
    scanner: Any,
    *,
    filename: str,
    content: bytes,
    content_type: str,
    security_error_factory: Callable[[str], TSecurityError],
    warn: Callable[[str, str, str, str], None] | None = None,
) -> None:
    """Run a scanner and raise for infected files.

    The scanner is intentionally structural: it only needs an async ``scan``
    method returning an object with ``verdict``, ``scanner_name``, ``detail``,
    and ``threat_name`` attributes.
    """
    result = await scanner.scan(filename=filename, content=content, content_type=content_type)
    verdict = getattr(result, "verdict", "")
    if verdict == "INFECTED":
        raise security_error_factory(str(getattr(result, "threat_name", "") or "unknown"))
    if verdict == "UNSCANNABLE" and warn is not None:
        maybe_awaitable = warn(
            str(getattr(result, "scanner_name", "")),
            filename,
            str(getattr(result, "detail", "")),
            verdict,
        )
        if isinstance(maybe_awaitable, Awaitable):
            await maybe_awaitable
