"""Helpers for extracting JSON objects from LLM-style responses."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass

from pydantic import BaseModel

from aha_common_utils.ports.types import JsonObject

REQUEST_ID_HEADERS = ("x-request-id", "request-id", "x-trace-id")


def safe_response_text(exc: Exception) -> str:
    """Return response text from an exception when present."""
    try:
        return str(exc.response.text)  # type: ignore[attr-defined]
    except Exception:
        return ""


def extract_content(response: object) -> str:
    """Extract text content from an AIMessage-like object or dict."""
    content = getattr(response, "content", None)
    if content is None and isinstance(response, dict):
        content = response.get("content")
    return str(content or "")


def parse_json_content(response: object) -> JsonObject:
    """Parse JSON object content from an AIMessage-like response."""
    content = extract_content(response)
    payload = try_parse_json(content)
    if payload is not None:
        return payload
    json_block = extract_json_block(content)
    if json_block is not None:
        return json_block
    raise ValueError("LLM structured response was not valid JSON")


def try_parse_json(content: str) -> JsonObject | None:
    """Parse a JSON object from a string, returning None for non-object JSON."""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def extract_json_block(content: str) -> JsonObject | None:
    """Extract the first JSON object from markdown-fenced or mixed text content."""
    for pattern in (r"```(?:json)?\s*\n(.*?)\n```", r"\{.*\}", r"\[.*\]"):
        match = re.search(pattern, content, re.DOTALL)
        if match:
            result = try_parse_json(match.group(1) if match.lastindex else match.group(0))
            if result is not None:
                return result
    return None


def coerce_json_object(response: object) -> JsonObject:
    """Coerce Pydantic, dataclass, dict, or text response into a JsonObject."""
    if isinstance(response, BaseModel):
        payload = response.model_dump()
    elif is_dataclass(response) and not isinstance(response, type):
        payload = asdict(response)
    elif isinstance(response, dict):
        payload = response
    else:
        return parse_json_content(response)

    if not all(isinstance(key, str) for key in payload):
        raise ValueError("LLM structured response object keys must be strings")
    return dict(payload)


def extract_request_id_from_exception(exc: Exception) -> str | None:
    """Extract a request id from an exception response headers object."""
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    get = getattr(headers, "get", None)
    if not callable(get):
        return None
    for name in REQUEST_ID_HEADERS:
        value = get(name) or get(name.title())
        if value:
            return str(value)
    return None
