"""统一配置入口 — AppConfig + 统一读写 API。

整合 SecureBaseSettings、ConfigLoader、ProviderRegistry 的配置加载能力，
提供单一入口点用于所有配置操作。

此模块使用 ``__path__`` 将 ``settings/`` 目录注册为子模块搜索路径，
因此 ``aha_common_utils.settings._base`` 等内部模块依然可正常导入。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# ── 将 settings/ 目录注册为子模块搜索路径 ──────────────────
# 必须在 settings._* 导入之前设置，否则 import 系统会将此模块视为
# 普通模块（而非 package），导致 settings._base 等子模块无法导入。
__path__ = [str(Path(__file__).parent / "settings")]

from aha_common_utils.config_file_parser import merge_configs as _merge_configs
from aha_common_utils.config_file_parser import read_config as _read_config
from aha_common_utils.config_file_parser import write_config as _write_config
from aha_common_utils.settings._base import SecureBaseSettings
from aha_common_utils.settings._constants import (
    INSECURE_DEFAULT_VALUES,
    SENSITIVE_SUBSTRINGS,
    is_sensitive_field,
    mask_value,
)
from aha_common_utils.settings._discovery import (
    build_env_specific_local_file,
    build_json_config_files,
    build_layered_env_files,
    build_sensitive_env_file,
    build_toml_config_files,
    build_yaml_config_files,
    find_project_root,
)
from pydantic_settings import SettingsConfigDict


class AppConfig(SecureBaseSettings):
    """统一应用配置基类。

    整合 YAML + TOML + JSON + .env.local + 进程环境变量的分层加载。
    继承 SecureBaseSettings 的敏感字段保护和生产环境校验。
    """

    model_config = SettingsConfigDict(
        yaml_file=build_yaml_config_files(),
        toml_file=build_toml_config_files(),
        json_file=build_json_config_files(),
        case_sensitive=False,
        env_ignore_empty=True,
        env_nested_delimiter="__",
        extra="ignore",
    )


def read_config(config_file: str | Path, *, path: str | None = None) -> dict[str, Any]:
    """统一读入口。根据扩展名自动选择解析器。

    Args:
        config_file: 配置文件路径（.yaml/.yml/.toml/.json/.ini/.cfg/.env）。
        path: 点号分隔的嵌套路径。TODO(Task 2): 底层支持后启用。

    Returns:
        配置字典。path 非空时仅返回嵌套子树的配置。
    """
    # TODO(Task 2): 将 path 参数传递给 _read_config 以支持嵌套子树提取
    return _read_config(config_file)


def write_config(
    data: dict[str, Any],
    config_file: str | Path,
    *,
    path: str | None = None,
    style: str | None = None,
) -> None:
    """统一写入口。根据扩展名自动选择序列化器。

    Args:
        data: 要写入的配置字典。
        config_file: 目标文件路径。
        path: 点号分隔的嵌套路径。TODO(Task 2): 底层支持后启用部分更新。
        style: 覆盖扩展名推断的格式。TODO(Task 2): 底层支持后启用。
    """
    # TODO(Task 2): 将 path 和 style 参数传递给 _write_config
    _write_config(data, config_file)


def merge_configs(*configs: dict[str, Any]) -> dict[str, Any]:
    """深度合并多个配置字典。后者覆盖前者。嵌套 dict 递归合并。"""
    return _merge_configs(*configs)


__all__ = [
    # ── 核心类 ──
    "AppConfig",
    "SecureBaseSettings",
    # ── 字段识别 ──
    "SENSITIVE_SUBSTRINGS",
    "INSECURE_DEFAULT_VALUES",
    "is_sensitive_field",
    "mask_value",
    # ── 文件发现 ──
    "find_project_root",
    "build_toml_config_files",
    "build_yaml_config_files",
    "build_json_config_files",
    "build_sensitive_env_file",
    "build_env_specific_local_file",
    "build_layered_env_files",
    # ── 统一读写 API ──
    "read_config",
    "write_config",
    "merge_configs",
]
