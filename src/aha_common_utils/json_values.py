"""Small helpers for normalizing JSON-like values."""

from __future__ import annotations


def flatten_numeric_list(value: object) -> list[float]:
    """Flatten a nested JSON list into numeric values."""
    if not isinstance(value, list):
        return []
    result: list[float] = []
    for item in value:
        if isinstance(item, list):
            result.extend(flatten_numeric_list(item))
        elif isinstance(item, int | float):
            result.append(float(item))
        elif isinstance(item, str):
            try:
                result.append(float(item))
            except (ValueError, TypeError):
                pass
    return result
