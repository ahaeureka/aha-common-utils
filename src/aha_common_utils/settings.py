"""Unified config I/O entry point — delegates to config_file_parser.

NOTE: SecureBaseSettings has been removed. New code should use:
  - ``BaseParameters`` (aha_common_utils.config_base)
  - ``ConfigStore`` (aha_common_utils.config_store)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aha_common_utils.config_base import BaseParameters
from aha_common_utils.config_file_parser import (
    merge_configs as _merge_configs,
)
from aha_common_utils.config_file_parser import (
    read_config as _read_config,
)
from aha_common_utils.config_file_parser import (
    write_config as _write_config,
)


def read_config(config_file: str | Path, *, path: str | None = None) -> dict[str, Any]:
    return _read_config(config_file, path=path)


def write_config(data, config_file, *, path=None, style=None):
    _write_config(data, config_file, path=path, style=style)


def merge_configs(*configs):
    return _merge_configs(*configs)


# Backward-compatible alias for projects that have not fully migrated.
SecureBaseSettings = BaseParameters


__all__ = ["read_config", "write_config", "merge_configs", "SecureBaseSettings"]
