"""向后兼容 shim — 请改用 ``aha_common_utils.settings``。

此模块仅用于维持旧导入路径的兼容性，不再是主要实现。
新代码请直接使用::

    from aha_common_utils.settings import SecureBaseSettings
    from aha_common_utils.settings import (
        build_toml_config_files,
        build_sensitive_env_file,
        build_layered_env_files,
    )

.. deprecated::
    直接从 ``aha_common_utils.layered_settings`` 导入已废弃，将在未来版本移除。
"""

from __future__ import annotations

from .settings import (
    SecureBaseSettings,
    build_layered_env_files,
    build_sensitive_env_file,
    build_toml_config_files,
    build_yaml_config_files,
)

__all__ = [
    "SecureBaseSettings",
    "build_toml_config_files",
    "build_yaml_config_files",
    "build_sensitive_env_file",
    "build_layered_env_files",
]
