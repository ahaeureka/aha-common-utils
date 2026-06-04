"""路径工具模块（已废弃）

提供项目路径相关的工具函数，包括：
- 查找项目根目录
- 递归查找 .env 文件

.. deprecated::
    请改用 ``aha_common_utils.settings._discovery`` 中的函数。
"""

import warnings
from pathlib import Path


def find_project_root(start_path: Path | None = None) -> Path:
    """（已废弃）查找项目根目录。

    请改用 ``aha_common_utils.settings._discovery.find_project_root()``。

    Args:
        start_path: 开始搜索的路径，默认为当前工作目录

    Returns:
        项目根目录路径
    """
    warnings.warn(
        "find_project_root() is deprecated. Use aha_common_utils.settings._discovery.find_project_root() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from aha_common_utils.settings._discovery import find_project_root as _fpr

    return _fpr(start=start_path)


def find_env_files_recursive(
    start_path: Path | None = None,
    env_filename: str = ".env",
) -> list[Path]:
    """（已废弃）递归查找 .env 文件。

    请改用 ``aha_common_utils.settings._discovery.build_sensitive_env_file()``。

    Args:
        start_path: 当前工作目录，默认为 cwd
        env_filename: 环境变量文件名，默认 '.env'

    Returns:
        .env 文件路径列表，按优先级从低到高排序
    """
    warnings.warn(
        "find_env_files_recursive() is deprecated. "
        "Use aha_common_utils.settings._discovery.build_sensitive_env_file() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from aha_common_utils.settings._discovery import build_sensitive_env_file

    result = build_sensitive_env_file()
    return [result] if result else []


__all__ = [
    "find_project_root",
    "find_env_files_recursive",
]
