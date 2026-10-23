"""Unified config I/O entry point — delegates to config_file_parser.

NOTE: SecureBaseSettings has been removed. New code should use:
  - ``BaseParameters`` (aha_common_utils.config_base)
  - ``ConfigStore`` (aha_common_utils.config_store)
"""

from __future__ import annotations

import warnings
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


#: 已移除基类的访问提示。保留名字只为让旧代码**响亮地**失败，而不是静默退化：
#: 旧代码会继承到这个纯 pydantic 基类，从而丢掉 pydantic-settings 的 env/dotenv 读取能力。
_DEPRECATION_MESSAGE = (
    "SecureBaseSettings 已被移除：它现在是纯 pydantic BaseParameters 的别名，"
    "不会读取环境变量或 dotenv —— 直接继承它并配置 SettingsConfigDict(env_prefix=...) "
    "会导致配置静默失效（永远返回代码默认值）。"
    "请迁移到 BaseParameters + ConfigStore，见 README「从 SecureBaseSettings 迁移」。"
)


def __getattr__(name: str) -> Any:
    """PEP 562：访问已移除的基类时发 DeprecationWarning（而非静默返回一个坏基类）。"""
    if name == "SecureBaseSettings":
        warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
        return BaseParameters
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["read_config", "write_config", "merge_configs"]
