"""Distill Utils - 通用工具模块

使用惰性导入避免包初始化阶段的循环依赖。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config_loader import ConfigLoader, load_config
    from .config_registry import (
        get_config_class,
        get_main_config_class,
        get_registry,
        register_config,
    )
    from .settings import (
        SecureBaseSettings,
        build_layered_env_files,
        build_toml_config_files,
        build_sensitive_env_file,
    )
    from .path_utils import find_env_files_recursive, find_project_root
    from .register import ProviderRegistry, register_provider, register_provider_group
    from .snowflake_id import (
        SnowflakeIDGenerator,
        generate_id,
        generate_ids,
        generate_string_id,
        generate_string_ids,
        parse_id,
        snowflake_id,
        snowflake_string_id,
    )
    from .tracing import get_tracer, setup_tracing
    from .logging import get_logger, setup_logging

__all__ = [
    # 配置系统
    "ConfigLoader",
    "load_config",
    "register_config",
    "get_registry",
    "get_config_class",
    "get_main_config_class",
    # 安全分层配置
    "SecureBaseSettings",
    "build_toml_config_files",
    "build_sensitive_env_file",
    "build_layered_env_files",  # 向后兼容
    # 路径工具
    "find_project_root",
    "find_env_files_recursive",
    # 注册相关
    "ProviderRegistry",
    "register_provider",
    "register_provider_group",
    # 追踪相关
    "setup_tracing",
    "get_tracer",
    # 雪花ID生成器
    "SnowflakeIDGenerator",
    "generate_id",
    "generate_ids",
    "generate_string_id",
    "generate_string_ids",
    "parse_id",
    "snowflake_id",
    "snowflake_string_id",
    # 日志相关
    "setup_logging",
    "get_logger",
]


def __getattr__(name: str) -> Any:
    if name in {"ConfigLoader", "load_config"}:
        from .config_loader import ConfigLoader, load_config

        return {"ConfigLoader": ConfigLoader, "load_config": load_config}[name]

    if name in {"register_config", "get_registry", "get_config_class", "get_main_config_class"}:
        from .config_registry import get_config_class, get_main_config_class, get_registry, register_config

        return {
            "register_config": register_config,
            "get_registry": get_registry,
            "get_config_class": get_config_class,
            "get_main_config_class": get_main_config_class,
        }[name]

    if name in {"find_project_root", "find_env_files_recursive"}:
        from .path_utils import find_env_files_recursive, find_project_root

        return {"find_project_root": find_project_root, "find_env_files_recursive": find_env_files_recursive}[name]

    if name in {"ProviderRegistry", "register_provider", "register_provider_group"}:
        from .register import ProviderRegistry, register_provider, register_provider_group

        return {
            "ProviderRegistry": ProviderRegistry,
            "register_provider": register_provider,
            "register_provider_group": register_provider_group,
        }[name]

    if name in {
        "SnowflakeIDGenerator",
        "generate_id",
        "generate_ids",
        "generate_string_id",
        "generate_string_ids",
        "parse_id",
        "snowflake_id",
        "snowflake_string_id",
    }:
        from .snowflake_id import (
            SnowflakeIDGenerator,
            generate_id,
            generate_ids,
            generate_string_id,
            generate_string_ids,
            parse_id,
            snowflake_id,
            snowflake_string_id,
        )

        return {
            "SnowflakeIDGenerator": SnowflakeIDGenerator,
            "generate_id": generate_id,
            "generate_ids": generate_ids,
            "generate_string_id": generate_string_id,
            "generate_string_ids": generate_string_ids,
            "parse_id": parse_id,
            "snowflake_id": snowflake_id,
            "snowflake_string_id": snowflake_string_id,
        }[name]

    if name in {"setup_tracing", "get_tracer"}:
        from .tracing import get_tracer, setup_tracing

        return {"setup_tracing": setup_tracing, "get_tracer": get_tracer}[name]

    if name in {"SecureBaseSettings", "build_layered_env_files", "build_toml_config_files", "build_sensitive_env_file"}:
        from .settings import (
            SecureBaseSettings,
            build_layered_env_files,
            build_sensitive_env_file,
            build_toml_config_files,
        )
        return {
            "SecureBaseSettings": SecureBaseSettings,
            "build_layered_env_files": build_layered_env_files,
            "build_toml_config_files": build_toml_config_files,
            "build_sensitive_env_file": build_sensitive_env_file,
        }[name]

    raise AttributeError(f"module '' has no attribute '{name}'")
