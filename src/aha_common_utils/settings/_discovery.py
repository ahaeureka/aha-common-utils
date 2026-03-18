"""配置文件与敏感 env 文件的自动发现工具。

提供：
- ``find_project_root``        — 向上查找包含 pyproject.toml 的目录
- ``build_toml_config_files``  — 返回可提交的 TOML 配置文件列表
- ``build_yaml_config_files``  — 返回可提交的 YAML 配置文件列表
- ``build_sensitive_env_file`` — 返回 .env.local（已 .gitignore）路径
- ``build_layered_env_files``  — 向后兼容旧接口
"""

from __future__ import annotations

import os
from pathlib import Path

from ..logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "find_project_root",
    "build_toml_config_files",
    "build_yaml_config_files",
    "build_sensitive_env_file",
    "build_layered_env_files",
]


# ---------------------------------------------------------------------------
# 项目根目录定位
# ---------------------------------------------------------------------------


def find_project_root(start: Path | None = None) -> Path:
    """从 ``start``（默认 cwd）向上查找包含 ``pyproject.toml`` 的最近目录。

    Args:
        start: 起始路径，默认为当前工作目录。

    Returns:
        找到的项目根目录；若一直到文件系统根目录都没找到，返回 ``start``。

    Examples:
        >>> root = find_project_root()
        >>> (root / "pyproject.toml").exists()
        True
    """
    current = (start or Path.cwd()).resolve()
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    return (start or Path.cwd()).resolve()


# ---------------------------------------------------------------------------
# TOML 配置文件（非敏感，可提交）
# ---------------------------------------------------------------------------


def build_toml_config_files(
    base_dir: Path | None = None,
    app_env: str | None = None,
) -> list[Path]:
    """返回应加载的 TOML 配置文件列表（仅包含磁盘上实际存在的文件）。

    加载顺序（优先级从低→高）：

    1. ``config.toml``             — 基础非敏感默认值，**可提交版本库**
    2. ``config.<app_env>.toml``   — 环境专属覆盖，**可提交版本库**

    .. important::
        TOML 文件中 **不应包含** 密码、API Key 等敏感信息。
        敏感信息请放入 ``.env.local``（已 .gitignore）或进程环境变量。

    Args:
        base_dir: 查找目录；为 None 时自动定位项目根目录（含 pyproject.toml）。
        app_env:  环境标识符；为 None 时读取 ``APP_ENV`` 环境变量（默认 development）。

    Returns:
        存在的 TOML 文件 ``Path`` 列表，按优先级从低到高排列。

    Examples:
        >>> files = build_toml_config_files()
        >>> [f.name for f in files]
        ['config.toml', 'config.development.toml']
    """
    if base_dir is None:
        base_dir = find_project_root()
    if app_env is None:
        app_env = os.environ.get("APP_ENV", "development").strip().lower()

    candidates: list[Path] = [
        base_dir / "config.toml",
        base_dir / f"config.{app_env}.toml",
    ]
    existing = [p for p in candidates if p.is_file()]

    if existing:
        logger.debug(
            "[toml_config] APP_ENV=%r, 加载 TOML 文件（低→高优先级）: %s",
            app_env,
            [p.name for p in existing],
        )
    else:
        logger.debug("[toml_config] APP_ENV=%r, 未在 %s 中找到任何 config.toml", app_env, base_dir)

    return existing


# ---------------------------------------------------------------------------
# YAML 配置文件（非敏感，可提交）
# ---------------------------------------------------------------------------


def build_yaml_config_files(
    base_dir: Path | None = None,
    app_env: str | None = None,
) -> list[Path]:
    """返回应加载的 YAML 配置文件列表（仅包含磁盘上实际存在的文件）。

    加载顺序（优先级从低→高）：

    1. ``config.yaml`` / ``config.yml``             — 基础非敏感默认值
    2. ``config.<app_env>.yaml`` / ``config.<app_env>.yml``   — 环境专属覆盖

    .. important::
        YAML 文件中 **不应包含** 密码、API Key 等敏感信息。
        敏感信息请放入 ``.env.local``（已 .gitignore）或进程环境变量。

    Args:
        base_dir: 查找目录；为 None 时自动定位项目根目录（含 pyproject.toml）。
        app_env:  环境标识符；为 None 时读取 ``APP_ENV`` 环境变量（默认 development）。

    Returns:
        存在的 YAML 文件 ``Path`` 列表，按优先级从低到高排列。

    Examples:
        >>> files = build_yaml_config_files()
        >>> [f.name for f in files]  # doctest: +SKIP
        ['config.yaml', 'config.development.yaml']
    """
    if base_dir is None:
        base_dir = find_project_root()
    if app_env is None:
        app_env = os.environ.get("APP_ENV", "development").strip().lower()

    # 对每个优先级层级只取第一个存在的（.yaml 优先于 .yml）
    existing: list[Path] = []
    # 基础配置：config.yaml 或 config.yml
    for p in [base_dir / "config.yaml", base_dir / "config.yml"]:
        if p.is_file():
            existing.append(p)
            break
    # 环境配置：config.<env>.yaml 或 config.<env>.yml
    for p in [base_dir / f"config.{app_env}.yaml", base_dir / f"config.{app_env}.yml"]:
        if p.is_file():
            existing.append(p)
            break

    if existing:
        logger.debug(
            "[yaml_config] APP_ENV=%r, 加载 YAML 文件（低→高优先级）: %s",
            app_env,
            [p.name for p in existing],
        )
    else:
        logger.debug("[yaml_config] APP_ENV=%r, 未在 %s 中找到任何 config.yaml/yml", app_env, base_dir)
    return existing


# ---------------------------------------------------------------------------
# 敏感 env 文件（.env.local，已 .gitignore）
# ---------------------------------------------------------------------------


def build_sensitive_env_file(
    base_dir: Path | None = None,
) -> Path | None:
    """返回 ``.env.local`` 的路径（若存在），否则返回 ``None``。

    ``.env.local`` 是 **唯一** 应存放敏感配置值（密码/API Key 等）的文件，
    且应被加入 ``.gitignore``，**绝不提交到版本库**。

    Args:
        base_dir: 查找目录，默认为项目根目录。

    Returns:
        存在时返回绝对路径，否则返回 ``None``。

    Examples:
        >>> p = build_sensitive_env_file()
        >>> p is None or p.name == ".env.local"
        True
    """
    if base_dir is None:
        base_dir = find_project_root()
    env_local = base_dir / ".env.local"
    if env_local.is_file():
        logger.debug("[sensitive_env] 找到 .env.local: %s", env_local)
        return env_local
    return None


# ---------------------------------------------------------------------------
# 向后兼容
# ---------------------------------------------------------------------------


def build_layered_env_files(
    base_dir: Path | None = None,
    app_env: str | None = None,  # noqa: ARG001
) -> list[str]:
    """已废弃 — 仅返回 ``.env.local``（若存在）的路径列表。

    原先同时返回 ``.env`` / ``.env.<APP_ENV>``，现已迁移至 TOML 文件，
    请改用 :func:`build_toml_config_files` + :func:`build_sensitive_env_file`。
    """
    p = build_sensitive_env_file(base_dir)
    return [str(p)] if p else []
