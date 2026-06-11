"""ConfigStore — unified config I/O facade.

Replaces pydantic-settings' ``settings_customise_sources`` with a standalone
engine that discovers, loads, merges, interpolates, and saves configuration
files for ``BaseParameters`` subclasses.

Priority (low to high):

1. Code defaults (model field defaults)
2. ``config.yaml`` / ``config.yml`` + ``config.<ENV>.yaml`` / ``config.<ENV>.yml``
3. ``config.toml`` + ``config.<ENV>.toml``
4. ``.env.local`` values (loaded into ``os.environ`` via dotenv, ``override=False``)
5. ``.env.<ENV>.local`` values (loaded into ``os.environ`` via dotenv, ``override=False``)
6. Process environment variables (top-level keys only, type-coerced)
"""

from __future__ import annotations

import json as _json
import os
import re
from pathlib import Path
from typing import Any

from .config_base import BaseParameters
from .config_file_parser import load_env_file
from .logging import get_logger

logger = get_logger(__name__)

# ── Regex for ${env:VAR:-default} interpolation ──────────────────────────
_ENV_VAR_PATTERN = re.compile(r"\$\{env:([^:}]+)(?::-([^}]+))?\}")


# ── Helper: convert plain values to tomlkit types ─────────────────────────


def _to_tomlkit(value: Any) -> Any:
    """Recursively convert Python dicts/lists to tomlkit tables/arrays.

    Args:
        value: Any Python value (dict, list, or scalar).

    Returns:
        tomlkit equivalent if available, otherwise the value unchanged.
    """
    try:
        import tomlkit

        if isinstance(value, dict):
            table = tomlkit.table()
            for k, v in value.items():
                table[k] = _to_tomlkit(v)
            return table
        if isinstance(value, list):
            array = tomlkit.array()
            for item in value:
                array.append(_to_tomlkit(item))
            return array
    except ImportError:
        pass
    return value


# ── Helper: deep merge ────────────────────────────────────────────────────


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    """Recursively merge *override* into *base* in-place.

    Nested dicts are merged; all other values are replaced.
    """
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


# ── Helper: env-var interpolation ─────────────────────────────────────────


def _interpolate_env_vars(data: Any) -> Any:
    """Recursively resolve ``${env:VAR:-default}`` patterns in strings.

    Handles nested dicts, lists, and tuples. Non-string values are
    returned unchanged.

    Args:
        data: Any value that may contain env-var placeholders.

    Returns:
        Value with all env-var placeholders resolved against ``os.environ``.
    """
    if isinstance(data, str):
        return _ENV_VAR_PATTERN.sub(_env_replacer, data)
    if isinstance(data, dict):
        return {k: _interpolate_env_vars(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return type(data)(_interpolate_env_vars(v) for v in data)
    return data


def _env_replacer(match: re.Match[str]) -> str:
    """Replacement callback for ``_ENV_VAR_PATTERN.sub()``.

    Looks up the captured variable name in ``os.environ``; falls back to
    the ``:-default`` portion when present. If neither is available, the
    placeholder is returned unchanged.
    """
    var_name = match.group(1)
    default = match.group(2)
    env_value = os.environ.get(var_name)
    if env_value is not None:
        return env_value
    if default is not None:
        return default
    return match.group(0)


# ── Helper: type coercion for env overrides ───────────────────────────────


def _coerce_value(env_value: str, existing_value: Any) -> Any:
    """Coerce a string environment value to match the type of *existing_value*.

    Rules:
    - If *existing_value* is ``bool``, parse truthy/falsy strings.
    - If *existing_value* is ``int``, call ``int(env_value)``.
    - If *existing_value* is ``float``, call ``float(env_value)``.
    - Otherwise return the string unchanged.

    Args:
        env_value: Raw string from the process environment.
        existing_value: Current value in the merged config dict.

    Returns:
        Coerced value.
    """
    if isinstance(existing_value, bool):
        lower = env_value.lower()
        if lower in ("true", "1", "yes", "on"):
            return True
        if lower in ("false", "0", "no", "off"):
            return False
        return env_value
    if isinstance(existing_value, int):
        return int(env_value)
    if isinstance(existing_value, float):
        return float(env_value)
    return env_value


# ============================================================================
# File discovery helpers (moved from settings._discovery)
# ============================================================================


def _find_project_root(start: Path | None = None) -> Path:
    """Walk up from *start* (default cwd) to nearest dir containing ``pyproject.toml``."""
    current = (start or Path.cwd()).resolve()
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    return (start or Path.cwd()).resolve()


def _build_toml_config_files(
    base_dir: Path | None = None,
    app_env: str | None = None,
) -> list[Path]:
    """Return existing TOML config files: [config.toml, config.<env>.toml]."""
    if base_dir is None:
        base_dir = _find_project_root()
    if app_env is None:
        app_env = os.environ.get("APP_ENV", "development").strip().lower()

    candidates: list[Path] = [
        base_dir / "config.toml",
        base_dir / f"config.{app_env}.toml",
    ]
    existing = [p for p in candidates if p.is_file()]

    if existing:
        logger.debug(
            "[toml_config] APP_ENV=%r, loading TOML files (low->high): %s",
            app_env,
            [p.name for p in existing],
        )
    else:
        logger.debug("[toml_config] APP_ENV=%r, no config.toml found in %s", app_env, base_dir)
    return existing


def _build_yaml_config_files(
    base_dir: Path | None = None,
    app_env: str | None = None,
) -> list[Path]:
    """Return existing YAML config files: [config.yaml, config.<env>.yaml]."""
    if base_dir is None:
        base_dir = _find_project_root()
    if app_env is None:
        app_env = os.environ.get("APP_ENV", "development").strip().lower()

    existing: list[Path] = []
    for p in [base_dir / "config.yaml", base_dir / "config.yml"]:
        if p.is_file():
            existing.append(p)
            break
    for p in [base_dir / f"config.{app_env}.yaml", base_dir / f"config.{app_env}.yml"]:
        if p.is_file():
            existing.append(p)
            break

    if existing:
        logger.debug(
            "[yaml_config] APP_ENV=%r, loading YAML files (low->high): %s",
            app_env,
            [p.name for p in existing],
        )
    else:
        logger.debug("[yaml_config] APP_ENV=%r, no config.yaml/yml found in %s", app_env, base_dir)
    return existing


def _build_sensitive_env_file(
    base_dir: Path | None = None,
) -> Path | None:
    """Return path to ``.env.local`` if it exists, otherwise ``None``."""
    if base_dir is None:
        base_dir = _find_project_root()
    env_local = base_dir / ".env.local"
    if env_local.is_file():
        logger.debug("[sensitive_env] found .env.local: %s", env_local)
        return env_local
    return None


def _build_env_specific_local_file(
    base_dir: Path | None = None,
    app_env: str | None = None,
) -> Path | None:
    """Return path to ``.env.<APP_ENV>.local`` if it exists, otherwise ``None``."""
    if base_dir is None:
        base_dir = _find_project_root()
    if app_env is None:
        app_env = os.environ.get("APP_ENV", "development").strip().lower()

    env_specific = base_dir / f".env.{app_env}.local"
    if env_specific.is_file():
        logger.debug("[sensitive_env] found .env.%s.local: %s", app_env, env_specific)
        return env_specific
    return None


# ============================================================================
# ConfigStore
# ============================================================================


class ConfigStore:
    """Unified config I/O engine for ``BaseParameters`` subclasses.

    Discovers configuration files, loads and merges them by priority,
    resolves ``${env:VAR:-default}`` placeholders, applies process
    environment overrides with type coercion, and constructs the model.

    Also supports saving config back to files with optional partial
    (section-scoped) updates and comment-preserving TOML output via
    ``tomlkit``.

    Example:
        >>> from aha_common_utils.config_base import BaseParameters
        >>> from aha_common_utils.config_store import ConfigStore
        >>>
        >>> class AppCfg(BaseParameters):
        ...     host: str = "localhost"
        ...     port: int = 8080
        ...
        >>> store = ConfigStore()
        >>> cfg = store.load(AppCfg, base_dir=Path("/app"))
        >>> print(cfg.host)
        'localhost'
        >>> # Save with partial update of a section
        >>> store.save({"host": "0.0.0.0"}, "/app/config.toml", path="server")
    """

    def __init__(self) -> None:
        """Initialize an empty ConfigStore.

        ``_raw_data`` is ``None`` until a successful ``load()`` call.
        """
        self._raw_data: dict[str, Any] | None = None

    # ── raw_data property ─────────────────────────────────────────────────

    @property
    def raw_data(self) -> dict[str, Any] | None:
        """Return the raw merged dict from the last ``load()`` call.

        Used by ``ProviderRegistry`` sync to access pre-model config values.
        """
        return self._raw_data

    # ── load ──────────────────────────────────────────────────────────────

    def load(
        self,
        config_class: type[BaseParameters],
        *,
        base_dir: Path | None = None,
        app_env: str | None = None,
    ) -> BaseParameters:
        """Load, merge, and construct a config model from files and env.

        Priority (low to high):
        1. Code defaults (model field defaults)
        2. YAML files (config.yaml + config.<ENV>.yaml)
        3. TOML files (config.toml + config.<ENV>.toml)
        4. ``.env.local`` (loaded into ``os.environ``, ``override=False``)
        5. ``.env.<ENV>.local`` (loaded into ``os.environ``, ``override=False``)
        6. Process environment variables (top-level keys, type-coerced)

        Args:
            config_class: A ``BaseParameters`` subclass defining the config schema.
            base_dir: Directory to search for config files. When ``None``,
                auto-discovers the project root (containing ``pyproject.toml``).
            app_env: Environment identifier (e.g. ``"production"``). When
                ``None``, reads ``APP_ENV`` from the process environment
                (defaults to ``"development"``).

        Returns:
            An instance of *config_class* populated from all sources.
        """
        if base_dir is None:
            base_dir = _find_project_root()
        if app_env is None:
            app_env = os.environ.get("APP_ENV", "development").strip().lower()

        # 1. Discover config files
        yaml_files = self._discover_yaml_files(base_dir, app_env)
        toml_files = self._discover_toml_files(base_dir, app_env)

        # 2. Parse all files into dicts
        all_dicts: list[dict[str, Any]] = []
        for fpath in yaml_files:
            try:
                all_dicts.append(self._parse_file(fpath))
                logger.debug("[ConfigStore] parsed YAML: %s", fpath.name)
            except Exception as exc:
                logger.warning("[ConfigStore] failed to parse %s: %s", fpath, exc)

        for fpath in toml_files:
            try:
                all_dicts.append(self._parse_file(fpath))
                logger.debug("[ConfigStore] parsed TOML: %s", fpath.name)
            except Exception as exc:
                logger.warning("[ConfigStore] failed to parse %s: %s", fpath, exc)

        # 3. Merge by priority (low to high) with recursive deep merge
        merged: dict[str, Any] = {}
        for d in all_dicts:
            _deep_merge(merged, d)

        # 4. Preserve raw merged dict
        self._raw_data = dict(merged)

        # 5. Load .env.local + .env.<ENV>.local into os.environ (override=False)
        self._load_env_files(base_dir, app_env)

        # 6. Walk merged dict and resolve ${env:VAR:-default} patterns
        merged = _interpolate_env_vars(merged)
        if not isinstance(merged, dict):
            merged = {}

        # 7. Apply process env overrides for top-level keys with type coercion
        self._apply_env_overrides(merged)

        # 8. Construct model via from_dict (handles its own env-var interpolation)
        instance = config_class.from_dict(merged, ignore_extra_fields=True)

        return instance

    # ── save ──────────────────────────────────────────────────────────────

    def save(
        self,
        config: BaseParameters | dict[str, Any],
        target: str | Path,
        *,
        path: str | None = None,
        format: str | None = None,  # noqa: A002
    ) -> None:
        """Save configuration to a file.

        Args:
            config: A ``BaseParameters`` instance or plain dict to persist.
            target: File path to write to.
            path: Optional dot-separated path for a partial (section-scoped)
                update. When provided, the existing file is read, the
                specified section is modified, and the whole file is written
                back.
            format: Output format (``"toml"``, ``"yaml"``, ``"json"``).
                Inferred from the file extension when ``None``.

        Raises:
            ValueError: If the format cannot be determined or is unsupported.
        """
        # Convert BaseParameters to plain dict
        data: dict[str, Any]
        if isinstance(config, BaseParameters):
            data = config.to_dict()
        else:
            data = config

        target_path = Path(target)

        # Resolve format
        fmt = (format or "").lstrip(".") or target_path.suffix.lstrip(".")
        if not fmt:
            raise ValueError(
                f"Cannot determine format for {target_path!s}; pass format= explicitly."
            )

        # Partial update path
        if path:
            self._partial_update(target_path, data, path, fmt)
            return

        # Full write
        os.makedirs(target_path.parent, exist_ok=True)

        if fmt in ("yaml", "yml"):
            self._write_yaml(target_path, data)
        elif fmt == "toml":
            self._write_toml(target_path, data)
        elif fmt == "json":
            self._write_json(target_path, data)
        else:
            raise ValueError(
                f"Unsupported format {fmt!r}. Supported: yaml, yml, toml, json."
            )

    # ── Internal: file discovery ──────────────────────────────────────────

    def _discover_yaml_files(
        self, base_dir: Path, app_env: str
    ) -> list[Path]:
        """Discover YAML config files: [config.yaml, config.<env>.yaml]."""
        return _build_yaml_config_files(base_dir=base_dir, app_env=app_env)

    def _discover_toml_files(
        self, base_dir: Path, app_env: str
    ) -> list[Path]:
        """Discover TOML config files: [config.toml, config.<env>.toml]."""
        return _build_toml_config_files(base_dir=base_dir, app_env=app_env)

    # ── Internal: file parsing ────────────────────────────────────────────

    @staticmethod
    def _parse_file(path: Path) -> dict[str, Any]:
        """Parse a single config file, dispatching on its extension.

        Supports ``.yaml``, ``.yml``, ``.toml``, ``.json``.

        Args:
            path: Path to the config file.

        Returns:
            Parsed dict (empty dict on failure).

        Raises:
            ValueError: If the format is unsupported.
        """
        suffix = path.suffix.lower()
        if suffix in (".yaml", ".yml"):
            import yaml

            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        if suffix == ".toml":
            import tomli

            with open(path, "rb") as f:
                return tomli.load(f)
        if suffix == ".json":
            with open(path, encoding="utf-8") as f:
                return _json.load(f)
        raise ValueError(f"Unsupported config file format: {suffix}")

    # ── Internal: env file loading ────────────────────────────────────────

    @staticmethod
    def _load_env_files(base_dir: Path, app_env: str) -> None:
        """Load ``.env.local`` and ``.env.<ENV>.local`` into ``os.environ``.

        Uses ``python-dotenv`` when available (falls back to a simple
        line parser). Existing environment variables are never overwritten
        (``override=False``).

        Args:
            base_dir: Project root directory.
            app_env: Environment identifier (e.g. ``"development"``).
        """
        # .env.local (lower priority)
        env_local = _build_sensitive_env_file(base_dir=base_dir)
        if env_local is not None:
            load_env_file(env_local, override=False)
            logger.debug("[ConfigStore] loaded env file: %s", env_local.name)

        # .env.<ENV>.local (higher priority, overrides .env.local)
        env_specific = _build_env_specific_local_file(base_dir=base_dir, app_env=app_env)
        if env_specific is not None:
            load_env_file(env_specific, override=True)
            logger.debug("[ConfigStore] loaded env file: %s", env_specific.name)

    # ── Internal: env overrides ───────────────────────────────────────────

    # Backward-compatible env prefix: old pydantic-settings used W5_FLOW_
    _LEGACY_ENV_PREFIXES: tuple[str, ...] = ("W5_FLOW_",)

    @staticmethod
    def _apply_env_overrides(merged: dict[str, Any]) -> None:
        """Apply process environment variables as overrides.

        Environment variables whose names match either a top-level key
        or a known ``validation_alias`` of a nested field are routed to
        the correct location in *merged*.  Legacy ``W5_FLOW_`` prefix is
        automatically stripped before matching.

        Values are type-coerced to match the existing value's type
        (bool, int, float, or string).

        Args:
            merged: The merged configuration dict (mutated in-place).
        """
        for env_key, env_val in os.environ.items():
            # Strip legacy pydantic-settings prefix
            key = env_key
            for prefix in ConfigStore._LEGACY_ENV_PREFIXES:
                if key.startswith(prefix):
                    key = key[len(prefix):]
                    break

            if not key or key == env_key and key.startswith("W5_FLOW_"):
                # key unchanged and still has prefix — not a matchable key
                continue

            # Try top-level match first
            if key in merged:
                merged[key] = _coerce_value(env_val, merged[key])
                continue

            # Try nested routing via split: W5_FLOW_LLM_API_KEY → LLM_API_KEY
            # Match against known flat→nested paths from BaseParameters aliases
            # The before-validator on AppConfig will handle routing, so we
            # just need to ensure the flat key exists at top level for routing
            # Insert as a synthetic top-level key — from_dict will route it
            merged[key] = _coerce_value(env_val, merged.get(key, env_val))

    # ── Internal: writing helpers ─────────────────────────────────────────

    @staticmethod
    def _write_toml(path: Path, data: dict[str, Any]) -> None:
        """Write data as TOML, using tomlkit for comment-preserving output.

        Falls back to ``tomli_w`` if ``tomlkit`` is not installed.

        Args:
            path: Output file path.
            data: Configuration dict to write.
        """
        try:
            import tomlkit

            doc = tomlkit.document()
            for key, value in data.items():
                doc[key] = _to_tomlkit(value)
            with open(path, "w", encoding="utf-8") as f:
                tomlkit.dump(doc, f)
            logger.debug("[ConfigStore] wrote TOML (tomlkit): %s", path)
        except ImportError:
            import tomli_w

            with open(path, "wb") as f:
                tomli_w.dump(data, f)
            logger.debug("[ConfigStore] wrote TOML (tomli_w): %s", path)

    @staticmethod
    def _write_yaml(path: Path, data: dict[str, Any]) -> None:
        """Write data as YAML.

        Args:
            path: Output file path.
            data: Configuration dict to write.
        """
        import yaml

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        logger.debug("[ConfigStore] wrote YAML: %s", path)

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        """Write data as JSON with indentation.

        Args:
            path: Output file path.
            data: Configuration dict to write.
        """
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(data, f, indent=2, ensure_ascii=False)
        logger.debug("[ConfigStore] wrote JSON: %s", path)

    # ── Internal: partial update ──────────────────────────────────────────

    @staticmethod
    def _partial_update(
        target_path: Path,
        data: dict[str, Any],
        path: str,
        fmt: str,
    ) -> None:
        """Read-modify-write a config file, updating only the section at *path*.

        Reads the existing file, navigates into the dot-separated *path*,
        deep-merges *data* into that section, and writes the entire file back.

        Args:
            target_path: Path to the config file.
            data: New data to merge into the target section.
            path: Dot-separated path to the section (e.g. ``"llm"`` or
                ``"cache.diskcache"``).
            fmt: Output format (``"toml"``, ``"yaml"``, ``"yml"``, ``"json"``).

        Raises:
            FileNotFoundError: If the target file does not exist.
        """
        if not target_path.is_file():
            raise FileNotFoundError(f"Config file not found for partial update: {target_path}")

        # Read existing
        existing = ConfigStore._parse_file(target_path)

        # Navigate to the target section, creating intermediate dicts as needed
        current: dict[str, Any] = existing
        parts = path.split(".")
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            elif not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]

        # Merge data into the target section
        last = parts[-1]
        if isinstance(current.get(last), dict) and isinstance(data, dict):
            _deep_merge(current[last], data)
        else:
            current[last] = data

        # Write back
        os.makedirs(target_path.parent, exist_ok=True)
        if fmt in ("yaml", "yml"):
            ConfigStore._write_yaml(target_path, existing)
        elif fmt == "toml":
            ConfigStore._write_toml(target_path, existing)
        elif fmt == "json":
            ConfigStore._write_json(target_path, existing)
        else:
            raise ValueError(f"Unsupported format for partial update: {fmt!r}")


__all__ = [
    "ConfigStore",
    "_deep_merge",
    "_interpolate_env_vars",
    "_coerce_value",
    "_to_tomlkit",
]
