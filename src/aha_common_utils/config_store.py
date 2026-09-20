"""ConfigStore — unified config I/O facade.

Replaces pydantic-settings' ``settings_customise_sources`` with a standalone
engine that discovers, loads, merges, interpolates, and saves configuration
files for ``BaseParameters`` subclasses.

Priority (low to high):

1. Code defaults (model field defaults)
2. ``config.yaml`` / ``config.yml`` + ``config.<ENV>.yaml`` / ``config.<ENV>.yml``
3. ``config.toml`` + ``config.<ENV>.toml``
4. ``.env`` values (loaded into ``os.environ`` via dotenv, ``override=False``)
5. ``.env.local`` values (loaded into ``os.environ`` via dotenv, ``override=True``)
6. ``.env.<ENV>.local`` values (loaded into ``os.environ`` via dotenv, ``override=True``)
7. Process environment variables (top-level keys only, type-coerced)
"""

from __future__ import annotations

import json as _json
import os
import re
from pathlib import Path
from typing import Any, get_args

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


def _interpolate_env_vars(
    data: Any,
    *,
    unresolved: set[str] | None = None,
    blank_unresolved: bool = False,
) -> Any:
    """Recursively resolve ``${env:VAR:-default}`` patterns in strings.

    Handles nested dicts, lists, and tuples. Non-string values are
    returned unchanged.

    Args:
        data: Any value that may contain env-var placeholders.
        unresolved: Optional collector receiving the names of placeholders that
            had neither an environment value nor a ``:-default``.
        blank_unresolved: Replace an unresolved placeholder with an empty string
            instead of leaving the literal ``${env:NAME}``. Both choices make the
            miss observable (one via the report, one via a visibly wrong value);
            the default keeps the literal.

    Returns:
        Value with all env-var placeholders resolved against ``os.environ``.
    """
    if isinstance(data, str):
        return _ENV_VAR_PATTERN.sub(
            lambda match: _env_replacer(match, unresolved=unresolved, blank_unresolved=blank_unresolved),
            data,
        )
    if isinstance(data, dict):
        return {
            k: _interpolate_env_vars(v, unresolved=unresolved, blank_unresolved=blank_unresolved)
            for k, v in data.items()
        }
    if isinstance(data, (list, tuple)):
        return type(data)(
            _interpolate_env_vars(v, unresolved=unresolved, blank_unresolved=blank_unresolved) for v in data
        )
    return data


def _env_replacer(
    match: re.Match[str],
    *,
    unresolved: set[str] | None = None,
    blank_unresolved: bool = False,
) -> str:
    """Replacement callback for ``_ENV_VAR_PATTERN.sub()``.

    Looks up the captured variable name in ``os.environ``; falls back to
    the ``:-default`` portion when present. If neither is available, the name is
    recorded in *unresolved* (when a collector was supplied) and the placeholder
    is returned as-is — or as an empty string when *blank_unresolved* is set.
    """
    var_name = match.group(1)
    default = match.group(2)
    env_value = os.environ.get(var_name)
    if env_value is not None:
        return env_value
    if default is not None:
        return default
    if unresolved is not None:
        unresolved.add(var_name)
    return "" if blank_unresolved else match.group(0)


# ── Helper: type coercion for env overrides ───────────────────────────────


#: Truthy/falsy spellings accepted for a ``bool`` target. A superset of what
#: pydantic accepts, so no value pydantic would take is rejected here.
_TRUTHY_ENV_VALUES = frozenset({"true", "1", "yes", "on", "t", "y"})
_FALSY_ENV_VALUES = frozenset({"false", "0", "no", "off", "f", "n"})


def _unwrap_optional(annotation: Any) -> Any:
    """Return the single non-``None`` member of ``X | None`` (unchanged otherwise)."""
    members = [member for member in get_args(annotation) if member is not type(None)]
    return members[0] if len(members) == 1 else annotation


def _coerce_value(env_value: str, existing_value: Any, *, source: str | None = None) -> Any:
    """Coerce a string environment value to match the type of *existing_value*.

    Rules:
    - ``bool`` target: parse truthy/falsy spellings. An unparseable value raises
      ``ValueError`` naming *source*, so a bad value is attributed to the
      variable that carried it instead of surfacing as an anonymous field error.
    - ``int`` / ``float`` target: parse, falling back to the raw string when the
      text is not a plain number — pydantic then reports the offending field.
    - Otherwise return the string.

    Whitespace is stripped in every case. That is deliberate: incidental padding
    is a classic footgun (a trailing ``" # comment"`` once leaked into a secret),
    and no legitimate configuration value depends on leading/trailing spaces.

    Args:
        env_value: Raw string from the process environment.
        existing_value: Current value in the merged config dict, or the field's
            declared annotation when the path is known.
        source: Name of the variable the value came from, used in errors.

    Returns:
        Coerced value.
    """
    text = env_value.strip()
    kind = _target_kind(existing_value)
    if kind is bool:
        lower = text.lower()
        if lower in _TRUTHY_ENV_VALUES:
            return True
        if lower in _FALSY_ENV_VALUES:
            return False
        raise ValueError(f"{source or '环境变量'} 的取值 {env_value!r} 无法解析为 bool")
    if kind is int:
        try:
            return int(text)
        except ValueError:
            return text
    if kind is float:
        try:
            return float(text)
        except ValueError:
            return text
    return text


def _target_kind(value: Any) -> type | None:
    """Which scalar type *value* stands for — either as an annotation or as a value.

    Both forms reach :func:`_coerce_value`: a caller may pass the field's declared
    annotation (``bool``, the type) or the current value from the merged dict
    (``True``, an instance). ``isinstance(bool, bool)`` is ``False``, so the two
    cases must be distinguished explicitly — otherwise a typed override silently
    falls through and pydantic reports it as an anonymous field error instead.
    """
    if value is bool or isinstance(value, bool):
        return bool
    if value is int or isinstance(value, int):
        return int
    if value is float or isinstance(value, float):
        return float
    return None


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


def _build_base_env_file(
    base_dir: Path | None = None,
) -> Path | None:
    """Return path to ``.env`` if it exists, otherwise ``None``."""
    if base_dir is None:
        base_dir = _find_project_root()
    env_file = base_dir / ".env"
    if env_file.is_file():
        logger.debug("[sensitive_env] found .env: %s", env_file)
        return env_file
    return None


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
        self._unknown_keys: tuple[str, ...] = ()
        self._unresolved_placeholders: tuple[str, ...] = ()
        self._unknown_env_keys: tuple[str, ...] = ()
        self._dotenv_keys: frozenset[str] = frozenset()

    # ── raw_data property ─────────────────────────────────────────────────

    @property
    def raw_data(self) -> dict[str, Any] | None:
        """Return the raw merged dict from the last ``load()`` call.

        Used by ``ProviderRegistry`` sync to access pre-model config values.
        """
        return self._raw_data

    @property
    def unknown_keys(self) -> tuple[str, ...]:
        """Dotted paths of file-sourced config keys that match no model field.

        Computed from :attr:`raw_data` — the merged file snapshot taken
        **before** process-environment overrides. Comparing the final merged
        dict instead would flag every unrelated environment variable, because
        :meth:`_apply_env_overrides` auto-creates nested dicts for any
        ``A_B_C`` key it encounters.

        Empty until a successful :meth:`load`.
        """
        return self._unknown_keys

    @property
    def unresolved_placeholders(self) -> tuple[str, ...]:
        """Names referenced by ``${env:NAME}`` with no value and no ``:-default``.

        The configured value is left as the literal ``${env:NAME}`` — this
        report only makes the miss observable; it does not change semantics.

        Empty until a successful :meth:`load`.
        """
        return self._unresolved_placeholders

    @property
    def unknown_env_keys(self) -> tuple[str, ...]:
        """Process/dotenv keys that matched no field path of the model.

        Names are derived from the model (``SCOPE_KEY``), so a key that matches
        nothing is either a typo or a name left over from an older schema.
        Reporting it keeps that visible: the key is skipped rather than being
        guessed into a nested table nobody reads.

        Empty until a successful :meth:`load`.
        """
        return self._unknown_env_keys

    # ── load ──────────────────────────────────────────────────────────────

    def load(
        self,
        config_class: type[BaseParameters],
        *,
        base_dir: Path | None = None,
        app_env: str | None = None,
        reject_bare_env: bool = False,
        env_prefix: str | None = None,
        blank_unresolved_placeholders: bool = False,
        warn_unknown_keys: bool = False,
        warn_unresolved_placeholders: bool = False,
    ) -> BaseParameters:
        """Load, merge, and construct a config model from files and env.

        Priority (low to high):
        1. Code defaults (model field defaults)
        2. YAML files (config.yaml + config.<ENV>.yaml)
        3. TOML files (config.toml + config.<ENV>.toml)
        4. ``.env`` (loaded into ``os.environ``, ``override=False``)
        5. ``.env.local`` (loaded into ``os.environ``, ``override=True``)
        6. ``.env.<ENV>.local`` (loaded into ``os.environ``, ``override=True``)
        7. Process environment variables (top-level keys, type-coerced)

        Args:
            config_class: A ``BaseParameters`` subclass defining the config schema.
            base_dir: Directory to search for config files. When ``None``,
                auto-discovers the project root (containing ``pyproject.toml``).
            app_env: Environment identifier (e.g. ``"production"``). When
                ``None``, reads ``APP_ENV`` from the process environment
                (defaults to ``"development"``).
            reject_bare_env: When ``True``, only process-environment keys
                carrying *env_prefix* are routed into the config. Bare names
                are ignored — containers are full of unrelated variables whose
                names can collide with a config section. Defaults to ``False``
                so existing consumers keep their permissive behaviour.
            env_prefix: Prefix required when *reject_bare_env* is on
                (e.g. ``"QUNAPAI_"``). Required in that case: without it no key
                could ever be accepted, so the combination is rejected.
            warn_unknown_keys: Emit a warning listing :attr:`unknown_keys`.
                Defaults to ``False``; the report is populated either way.
            warn_unresolved_placeholders: Emit a warning listing
                :attr:`unresolved_placeholders`. Defaults to ``False``.

        Returns:
            An instance of *config_class* populated from all sources.
        """
        if base_dir is None:
            base_dir = _find_project_root()
        if app_env is None:
            app_env = os.environ.get("APP_ENV", "development").strip().lower()

        if reject_bare_env and not env_prefix:
            raise ValueError(
                "reject_bare_env=True requires env_prefix (otherwise no environment key could ever be accepted)"
            )

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

        # 5. Load .env + .env.local + .env.<ENV>.local into os.environ
        #
        # The dotenv chain is loaded *into the process environment* so that
        # ``${env:NAME}`` placeholders and the override step below can see it.
        # That mutation is undone before returning: a config loader must not
        # leave dotenv values (frequently secrets) in the process environment,
        # and leaving them behind makes two loads with different ``base_dir``
        # interfere with each other.
        pre_load_env = dict(os.environ)
        try:
            self._dotenv_keys = frozenset(self._load_env_files(base_dir, app_env))

            # 6. Walk merged dict and resolve ${env:VAR:-default} patterns
            unresolved: set[str] = set()
            merged = _interpolate_env_vars(
                merged,
                unresolved=unresolved,
                blank_unresolved=blank_unresolved_placeholders,
            )
            if not isinstance(merged, dict):
                merged = {}
            self._unresolved_placeholders = tuple(sorted(unresolved))

            # 7. Apply process env overrides for top-level keys with type coercion
            self._unknown_env_keys = self._apply_env_overrides(
                merged,
                reject_bare_env=reject_bare_env,
                env_prefix=env_prefix,
                config_class=config_class,
                dotenv_keys=self._dotenv_keys,
            )

            # 8. Construct model via from_dict (handles its own env-var interpolation)
            instance = config_class.from_dict(merged, ignore_extra_fields=True)
        finally:
            _restore_process_env(pre_load_env)

        # 9. Reports are always populated; the warnings are opt-in (silent by default)
        self._unknown_keys = _collect_unknown_keys(self._raw_data, config_class)
        _warn_about_reports(
            unknown_keys=self._unknown_keys,
            unresolved=self._unresolved_placeholders,
            warn_unknown_keys=warn_unknown_keys,
            warn_unresolved_placeholders=warn_unresolved_placeholders,
        )

        return instance

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
            raise ValueError(f"Cannot determine format for {target_path!s}; pass format= explicitly.")

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
            raise ValueError(f"Unsupported format {fmt!r}. Supported: yaml, yml, toml, json.")

    # ── Internal: file discovery ──────────────────────────────────────────

    def _discover_yaml_files(self, base_dir: Path, app_env: str) -> list[Path]:
        """Discover YAML config files: [config.yaml, config.<env>.yaml]."""
        return _build_yaml_config_files(base_dir=base_dir, app_env=app_env)

    def _discover_toml_files(self, base_dir: Path, app_env: str) -> list[Path]:
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
    def _load_env_files(base_dir: Path, app_env: str) -> set[str]:
        """Load ``.env``, ``.env.local``, and ``.env.<ENV>.local`` into ``os.environ``.

        Snapshots the process environment before loading any dotenv files,
        then restores all pre-existing keys (including empty strings) after
        loading.  This ensures that:

        - ``.env`` provides low-priority local defaults.
        - ``.env.local`` can override ``.env`` for local sensitive values.
        - Environment-specific dotenv can override base dotenv
          (``.env.<ENV>.local`` loaded with ``override=True``).
        - Process environment variables always retain highest priority,
          regardless of what dotenv files contain.

        Args:
            base_dir: Project root directory.
            app_env: Environment identifier (e.g. ``"development"``).
        """
        # Snapshot the current process environment before any dotenv loading
        pre_existing = dict(os.environ)

        # .env (lowest dotenv priority)
        env_file = _build_base_env_file(base_dir=base_dir)
        if env_file is not None:
            load_env_file(env_file, override=False)
            logger.debug("[ConfigStore] loaded env file: %s", env_file.name)

        # .env.local (higher priority than .env)
        env_local = _build_sensitive_env_file(base_dir=base_dir)
        if env_local is not None:
            load_env_file(env_local, override=True)
            logger.debug("[ConfigStore] loaded env file: %s", env_local.name)

        # .env.<ENV>.local (higher priority, overrides .env.local)
        env_specific = _build_env_specific_local_file(base_dir=base_dir, app_env=app_env)
        if env_specific is not None:
            load_env_file(env_specific, override=True)
            logger.debug("[ConfigStore] loaded env file: %s", env_specific.name)

        # Process environment always retains highest priority: restore every
        # pre-existing key, including the ones the override-sensitive dotenv
        # files (.env.local / .env.<ENV>.local) just changed.  Keys the process
        # environment did not define keep the value produced by the dotenv
        # chain, so `.env.local` can still override `.env`, and
        # `.env.<ENV>.local` can still override `.env.local`.
        # Record what the dotenv chain contributed *before* restoring the
        # snapshot: those keys are exempt from the bare-name rule, because the
        # project controls that chain itself.
        dotenv_keys = {key for key, value in os.environ.items() if pre_existing.get(key) != value}
        os.environ.update(pre_existing)
        return dotenv_keys

    # ── Internal: env overrides ───────────────────────────────────────────

    # Backward-compatible env prefix: old pydantic-settings used W5_FLOW_
    _LEGACY_ENV_PREFIXES: tuple[str, ...] = ("W5_FLOW_",)

    @staticmethod
    def _apply_env_overrides(
        merged: dict[str, Any],
        *,
        reject_bare_env: bool = False,
        env_prefix: str | None = None,
        config_class: type[BaseParameters] | None = None,
        dotenv_keys: frozenset[str] = frozenset(),
    ) -> tuple[str, ...]:
        """Apply process environment variables as overrides.

        A variable name is **derived from the model**, never looked up in a
        table: every leaf field path becomes ``SCOPE_KEY`` — its segments
        uppercased and joined with ``_``. So ``database.url`` reads
        ``DATABASE_URL``, ``llm.api_key`` reads ``LLM_API_KEY``, and
        ``s3_file_storage.access_key`` reads ``S3_FILE_STORAGE_ACCESS_KEY``.

        Deriving the name is what makes the rule unambiguous. Field names
        themselves contain underscores, so splitting a name back on ``_``
        cannot work (``LLM_API_KEY`` would become ``llm.api.key``); building the
        index from the model inverts the derivation exactly instead.

        A key that matches no field path is **not guessed at**: it is skipped
        and reported in the return value, so a typo or a stale name stays
        visible instead of silently creating an unused nested table.

        Values are type-coerced and whitespace-stripped.

        When *reject_bare_env* is set, keys carrying neither *env_prefix* nor a
        dotenv origin are skipped. That is an opt-in discipline for consumers
        whose deployments are full of unrelated variables: a bare ``DEBUG`` or
        ``DATABASE_URL`` coming from an unrelated tool would otherwise silently
        become configuration. Dotenv keys are exempt because that chain is
        controlled by the project itself, and prefix matching is
        case-insensitive because process-env spelling varies in practice.

        Args:
            merged: The merged configuration dict (mutated in-place).
            reject_bare_env: Skip keys with neither the prefix nor a dotenv origin.
            env_prefix: Required prefix when *reject_bare_env* is on.
            config_class: Model whose field paths define the accepted names.
            dotenv_keys: Keys supplied by the dotenv chain (exempt from the prefix rule).

        Returns:
            Names of the environment keys that matched no field path.
        """
        index = _env_name_index(config_class) if config_class is not None else {}
        unknown: list[str] = []

        # Two priority classes, applied in order: a prefixed process-env value
        # must always beat a dotenv-provided bare name (the documented
        # precedence). Both live in ``os.environ``, so without an explicit
        # ordering the winner would be whichever happened to be inserted last —
        # a bare name loaded from ``.env.local`` could silently override
        # ``QUNAPAI_X``.
        candidates: list[tuple[int, str, str, str]] = []

        for env_key, env_val in os.environ.items():
            # Strip legacy pydantic-settings prefix
            key = env_key
            for legacy in ConfigStore._LEGACY_ENV_PREFIXES:
                if key.startswith(legacy):
                    key = key[len(legacy) :]
                    break

            # Bind the stripped form so the type checker can follow the
            # ``env_prefix is not None`` narrowing into the slice below.
            stripped: str | None = None
            if env_prefix is not None and key.upper().startswith(env_prefix.upper()):
                stripped = key[len(env_prefix) :]
            if reject_bare_env and stripped is None and env_key not in dotenv_keys:
                continue
            if stripped is not None:
                key = stripped

            if not key or (key == env_key and key.startswith("W5_FLOW_")):
                continue

            candidates.append((1 if stripped is not None else 0, env_key, key, env_val))

        for _priority, env_key, key, env_val in sorted(candidates, key=lambda item: item[0]):
            path = index.get(key.upper())
            if path is None:
                unknown.append(env_key)
                continue

            annotation = _annotation_for_path(config_class, path)
            target = annotation if annotation is not None else _get_by_path(merged, path)
            _set_by_path(merged, path, _coerce_value(env_val, target, source=env_key))

        return tuple(sorted(unknown))


# ── Helper: derived environment names ──────────────────────────────────


def _env_name_index(model: type[BaseParameters]) -> dict[str, tuple[str, ...]]:
    """Map every leaf field path of *model* to its derived environment name.

    ``("llm", "api_key")`` → ``"LLM_API_KEY"``. Building the index from the
    model inverts the naming rule exactly, so no hand-written name table can
    drift out of sync with the schema.
    """
    index: dict[str, tuple[str, ...]] = {}

    def walk(current: type[BaseParameters], prefix: tuple[str, ...]) -> None:
        for name, field in current.model_fields.items():
            annotation = _unwrap_optional(field.annotation)
            path = (*prefix, name)
            if _is_group(annotation):
                walk(annotation, path)
            else:
                index["_".join(path).upper()] = path

    walk(model, ())
    return index


def _is_group(annotation: Any) -> bool:
    """Whether *annotation* is a nested ``BaseParameters`` group."""
    return isinstance(annotation, type) and issubclass(annotation, BaseParameters)


def _annotation_for_path(model: type[BaseParameters] | None, path: tuple[str, ...]) -> Any:
    """Declared annotation for a field *path*, or ``None`` when unresolvable."""
    current: Any = model
    for part in path:
        if not _is_group(current):
            return None
        field = current.model_fields.get(part)
        if field is None:
            return None
        current = _unwrap_optional(field.annotation)
    return current


def _get_by_path(merged: dict[str, Any], path: tuple[str, ...]) -> Any:
    """Current value at *path* inside *merged*, or ``None``."""
    node: Any = merged
    for part in path:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set_by_path(merged: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    """Assign *value* at the nested *path*, creating intermediate tables."""
    node = merged
    for part in path[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[path[-1]] = value

    # ── Internal: writing helpers ─────────────────────────────────────────


# ── Helper: reports behind the opt-in guards ────────────────────────────


def _collect_unknown_keys(
    raw_data: dict[str, Any] | None,
    config_class: type[BaseParameters],
) -> tuple[str, ...]:
    """Dotted paths in *raw_data* that match no field path of *config_class*.

    *raw_data* is the merged **file** snapshot, taken before process-environment
    overrides. The final merged dict cannot be used here: the override step
    auto-creates nested dicts for any ``A_B_C`` environment variable, so every
    unrelated variable would be reported and drown the signal.

    Recursion follows nested ``BaseParameters`` groups, so ``[database] url`` is
    checked against the group model rather than against a flattened name.
    """
    if not raw_data:
        return ()

    unknown: list[str] = []

    def walk(node: dict[str, Any], model: type[BaseParameters], prefix: str) -> None:
        fields = model.model_fields
        for key, value in node.items():
            path = f"{prefix}{key}"
            field = fields.get(key)
            if field is None:
                unknown.append(path)
                continue
            annotation = field.annotation
            if isinstance(annotation, type) and issubclass(annotation, BaseParameters):
                if isinstance(value, dict):
                    walk(value, annotation, f"{path}.")
                continue
            if isinstance(value, dict):
                # A table where a scalar was declared: nothing under it can be
                # consumed either, so report the leaves.
                unknown.extend(_leaf_paths(value, f"{path}."))

    walk(raw_data, config_class, "")
    return tuple(sorted(unknown))


def _leaf_paths(node: dict[str, Any], prefix: str) -> list[str]:
    """Dotted paths of every leaf value under *node*."""
    paths: list[str] = []
    for key, value in node.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            paths.extend(_leaf_paths(value, path + "."))
        else:
            paths.append(path)
    return paths


def _warn_about_reports(
    *,
    unknown_keys: tuple[str, ...],
    unresolved: tuple[str, ...],
    warn_unknown_keys: bool,
    warn_unresolved_placeholders: bool,
) -> None:
    """Emit the two opt-in warnings.

    Silent by default, so existing consumers keep their current behaviour while
    the reports stay populated for a consumer that renders its own diagnostic.
    """
    if warn_unknown_keys and unknown_keys:
        logger.warning(
            "[ConfigStore] 以下配置键没有对应字段，已被忽略：{}（如属笔误请修正，如属新增配置请先加字段）",
            ", ".join(unknown_keys),
        )
    if warn_unresolved_placeholders and unresolved:
        logger.warning(
            "[ConfigStore] 以下环境变量未设置且无默认值，占位符按字面量保留：{}（应在 .env.local 或进程环境注入）",
            ", ".join(unresolved),
        )


# ── Helper: process-environment hygiene ────────────────────────────────


def _restore_process_env(snapshot: dict[str, str]) -> None:
    """Restore ``os.environ`` to *snapshot*, dropping keys added since.

    ``_load_env_files`` only restores the keys it *changed*; keys the dotenv
    chain introduced stay behind. Dropping them here keeps
    :meth:`ConfigStore.load` free of a global side effect, while still letting
    placeholder resolution and the override step see dotenv values during the
    load. Without it a load leaks dotenv values into every later load — two
    loads with different ``base_dir`` would silently share them.
    """
    for key in [name for name in os.environ if name not in snapshot]:
        del os.environ[key]
    os.environ.update(snapshot)


__all__ = [
    "ConfigStore",
    "_deep_merge",
    "_interpolate_env_vars",
    "_coerce_value",
    "_to_tomlkit",
]
