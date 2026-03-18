"""aha_common_utils.settings — 安全分层配置公共 API。

推荐用法::

    from aha_common_utils.settings import SecureBaseSettings
    from pydantic_settings import SettingsConfigDict

    class AppSettings(SecureBaseSettings):
        model_config = SettingsConfigDict(env_prefix="MYAPP_")
        DATABASE_URL: str = "postgresql+asyncpg://localhost/dev"
        SECRET_KEY: str = "change-me-in-production"

    settings = AppSettings()
    print(settings.safe_dump())  # 敏感字段自动屏蔽

工具函数::

    from aha_common_utils.settings import (
        find_project_root,
        build_toml_config_files,
        build_sensitive_env_file,
    )
"""

from __future__ import annotations

from ._base import SecureBaseSettings
from ._constants import (
    INSECURE_DEFAULT_VALUES,
    SENSITIVE_SUBSTRINGS,
    is_sensitive_field,
    mask_value,
)
from ._discovery import (
    build_layered_env_files,
    build_sensitive_env_file,
    build_toml_config_files,
    build_yaml_config_files,
    find_project_root,
)

__all__ = [
    # 核心类
    "SecureBaseSettings",
    # 字段识别
    "SENSITIVE_SUBSTRINGS",
    "INSECURE_DEFAULT_VALUES",
    "is_sensitive_field",
    "mask_value",
    # 文件发现
    "find_project_root",
    "build_toml_config_files",
    "build_yaml_config_files",
    "build_sensitive_env_file",
    "build_layered_env_files",
]
