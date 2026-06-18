"""BaseParameters — pure-pydantic config base class replacing pydantic-settings SecureBaseSettings.

Provides env-var interpolation (``${env:VAR:-default}``), sensitive field
masking, production security validation, metadata-rich Field factory, and
dict/CLI serialization helpers.

This module is self-contained: it does NOT import from pydantic-settings,
w5-flow, glimmer, or any other project-specific package.
"""

from __future__ import annotations

import os
import re
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator
from pydantic.fields import FieldInfo

# ── Regex for ${env:VAR:-default} interpolation ──────────────────────
ENV_VAR_PATTERN = re.compile(r"\$\{env:([^:}]+)(?::-([^}]+))?\}")

# ── Sensitive-field constants ────────────────────────────────────────
SENSITIVE_SUBSTRINGS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "api_key",
        "apikey",
        "token",
        "private_key",
        "access_key",
        "secret_key",
        "dsn",
        "auth",
        "credential",
        "database_url",
        "redis_url",
    }
)

INSECURE_DEFAULT_VALUES: frozenset[str] = frozenset(
    {
        "change-me-in-production",
        "change_me_in_production",
        "changeme",
        "change_me",
        "secret",
        "password",
        "postgres",
        "admin",
        "your-secret-key",
        "your_secret_key",
        "dev-only",
    }
)


def is_sensitive_field(field_name: str) -> bool:
    """Determine whether a field name matches sensitive patterns.

    Args:
        field_name: Configuration field name (case-insensitive).

    Returns:
        True if the field may contain passwords, keys, or other secrets.

    Examples:
        >>> is_sensitive_field("DATABASE_URL")
        True
        >>> is_sensitive_field("LOG_LEVEL")
        False
    """
    name_lower = field_name.lower()
    return any(sub in name_lower for sub in SENSITIVE_SUBSTRINGS)


def mask_value(value: object) -> str:
    """Mask a value for safe display, keeping the first 4 characters for provenance.

    Args:
        value: Any value, converted to string.

    Returns:
        Masked string such as ``"sk-p****"`` or ``"****"``.

    Examples:
        >>> mask_value("sk-proj-abc123")
        'sk-p****'
        >>> mask_value("ab")
        '****'
    """
    s = str(value)
    if not s:
        return repr(value)
    return s[:4] + "****" if len(s) > 4 else "****"


# ── Internal helpers ──────────────────────────────────────────────────


def _field_is_fixed(field_info: FieldInfo) -> bool:
    """Check whether a field has the ``fixed`` tag in ``json_schema_extra``."""
    extra: dict[str, Any] = getattr(field_info, "json_schema_extra", None) or {}
    return bool(extra.get("fixed", False))


# ── BaseParameters ───────────────────────────────────────────────────


class BaseParameters(BaseModel):
    """Pure-pydantic config base class replacing pydantic-settings SecureBaseSettings.

    Features:

    1. ``${env:VAR:-default}`` interpolation on string values at init time.
    2. Sensitive-field masking in ``__repr__``, ``__str__``, and ``safe_dump()``.
    3. Production-security validation via ``_check_production_security``.
    4. Metadata-rich ``field()`` factory with ``fixed`` / ``tags`` support.
    5. Dict import/export, CLI-arg generation, and parameter descriptions.

    Subclasses may extend sensitive-field detection via
    ``_EXTRA_SENSITIVE_FIELDS: ClassVar[set[str]]``.

    Example:
        >>> class AppParams(BaseParameters):
        ...     app_name: str = "my-app"
        ...     api_key: str = BaseParameters.field(
        ...         "",
        ...         description="API key for external service",
        ...         tags=["sensitive"],
        ...     )
        ...     max_retries: int = BaseParameters.field(
        ...         3,
        ...         description="Max retry attempts",
        ...         fixed=True,
        ...     )
        >>> params = AppParams(api_key="sk-secret-123")
        >>> print(params)
        AppParams(app_name='my-app', api_key='sk-s****', max_retries=3)
    """

    model_config = ConfigDict(
        validate_assignment=True,
        use_enum_values=True,
    )

    _EXTRA_SENSITIVE_FIELDS: ClassVar[set[str]] = set()

    # ── Init with env-var interpolation ──────────────────────────────

    def __init__(self, **data: Any) -> None:
        """Initialize with env-var interpolation on all string values.

        String values (both passed data and model defaults) containing
        ``${env:VAR:-default}`` patterns are resolved against
        ``os.environ`` before pydantic validation.
        """
        resolved = {k: self._resolve_env_vars(v) for k, v in data.items()}
        super().__init__(**resolved)
        # Second pass: resolve env vars in fields that used their
        # default values (not supplied in *data*).
        for field_name in type(self).model_fields:
            if field_name in data:
                continue
            value = getattr(self, field_name, None)
            if isinstance(value, str):
                new_value = self._resolve_env_vars(value)
                if new_value is not value:
                    setattr(self, field_name, new_value)

    # ── Env-var resolution ───────────────────────────────────────────

    @classmethod
    def _resolve_env_vars(cls, value: Any) -> Any:
        """Recursively resolve ``${env:VAR:-default}`` patterns in strings.

        Handles nested dicts, lists, and tuples. Non-string values are
        returned unchanged.

        Args:
            value: Any value that may contain env-var placeholders.

        Returns:
            Value with all env-var placeholders resolved against
            ``os.environ``.
        """
        if isinstance(value, str):
            return ENV_VAR_PATTERN.sub(cls._env_replacer, value)
        if isinstance(value, dict):
            return {k: cls._resolve_env_vars(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return type(value)(cls._resolve_env_vars(v) for v in value)
        return value

    @staticmethod
    def _env_replacer(match: re.Match[str]) -> str:
        """Replacement callback for ``ENV_VAR_PATTERN.sub()``.

        Looks up the captured variable name in ``os.environ``; falls
        back to the ``:-default`` portion when present. If neither the
        environment variable nor a default is available, the placeholder
        is returned unchanged.
        """
        var_name = match.group(1)
        default = match.group(2)
        env_value = os.environ.get(var_name)
        if env_value is not None:
            return env_value
        if default is not None:
            return default
        return match.group(0)

    # ── Factory: from_dict ───────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict[str, Any], ignore_extra_fields: bool = False) -> BaseParameters:
        """Construct an instance from a dictionary with env-var interpolation.

        Args:
            data: Raw configuration dictionary whose string values may
                contain ``${env:VAR:-default}`` placeholders.
            ignore_extra_fields: When True, unknown keys are silently
                dropped via a ``create_model`` wrapper with
                ``extra="ignore"``.

        Returns:
            A new instance of the class.
        """
        resolved = {k: cls._resolve_env_vars(v) for k, v in data.items()}
        if not ignore_extra_fields:
            return cls(**resolved)

        # Build a temporary model with extra="ignore" to drop unknown keys.
        temp_model = create_model(
            f"_{cls.__name__}FromDict",
            __base__=cls,
        )
        if isinstance(temp_model.model_config, dict):
            temp_model.model_config = {**temp_model.model_config, "extra": "ignore"}
        else:
            temp_model.model_config = ConfigDict(extra="ignore")
        return temp_model(**resolved)

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entire config to a plain dict.

        Uses ``model_dump(by_alias=False)`` so keys are always the
        Python attribute names.
        """
        return self.model_dump(by_alias=False)

    # ── Update / merge ───────────────────────────────────────────────

    def update_from(self, source: BaseParameters | dict[str, Any]) -> bool:
        """Merge values from another instance or dict.

        Fields marked as ``fixed`` (via ``json_schema_extra``) are
        skipped and retain their current values.  ``None`` values in
        the source are also skipped to avoid overwriting required
        fields.

        Args:
            source: Another ``BaseParameters`` instance or a plain
                ``dict`` of field values.

        Returns:
            ``True`` if at least one field was updated.

        Raises:
            TypeError: If *source* is neither ``BaseParameters`` nor
                ``dict``.
        """
        if isinstance(source, BaseParameters):
            source_data = source.to_dict()
        elif isinstance(source, dict):
            source_data = source
        else:
            raise TypeError(f"source must be BaseParameters or dict, got {type(source).__name__}")

        updated = False
        for field_name, field_info in type(self).model_fields.items():
            if _field_is_fixed(field_info):
                continue
            if field_name in source_data:
                new_value = source_data[field_name]
                if new_value is not None and new_value != getattr(self, field_name):
                    setattr(self, field_name, new_value)
                    updated = True
        return updated

    # ── Sensitive-field detection ────────────────────────────────────

    def _field_is_sensitive(self, field_name: str) -> bool:
        """Check whether a field is sensitive.

        Combines pattern-based detection (``is_sensitive_field``) with
        the subclass ``_EXTRA_SENSITIVE_FIELDS`` set.
        """
        return is_sensitive_field(field_name) or field_name.lower() in {f.lower() for f in self._EXTRA_SENSITIVE_FIELDS}

    # ── Safe display ─────────────────────────────────────────────────

    def __repr__(self) -> str:
        """Safe repr with sensitive-fields masked."""
        parts: list[str] = []
        for field_name in type(self).model_fields:
            value = getattr(self, field_name, None)
            if self._field_is_sensitive(field_name) and value:
                parts.append(f"{field_name}={mask_value(value)}")
            else:
                parts.append(f"{field_name}={value!r}")
        return f"{self.__class__.__name__}({', '.join(parts)})"

    def __str__(self) -> str:
        """Safe str — delegates to ``__repr__``."""
        return self.__repr__()

    def safe_dump(self) -> dict[str, Any]:
        """Return a dict with sensitive fields masked.

        Recursively handles nested ``BaseParameters`` sub-models and
        lists of sub-models.

        Returns:
            Dict where sensitive values are replaced with masked strings.

        Examples:
            >>> params.safe_dump()
            {'APP_ENV': 'development', 'DATABASE_URL': 'post****', ...}
        """
        result: dict[str, Any] = {}
        for field_name in type(self).model_fields:
            value = getattr(self, field_name, None)
            if self._field_is_sensitive(field_name) and value:
                result[field_name] = mask_value(value)
            elif isinstance(value, BaseParameters):
                result[field_name] = value.safe_dump()
            elif isinstance(value, list):
                result[field_name] = [v.safe_dump() if isinstance(v, BaseParameters) else v for v in value]
            else:
                result[field_name] = value
        return result

    # ── Production security ──────────────────────────────────────────

    @model_validator(mode="after")
    def _check_production_security(self) -> BaseParameters:
        """Fail fast in production when sensitive fields hold insecure defaults.

        Only active when ``APP_ENV`` is ``production``. Raises
        ``ValueError`` if any sensitive field still contains a known
        insecure default (e.g. ``"change-me-in-production"``).
        """
        app_env = os.environ.get("APP_ENV", "development").strip().lower()
        if app_env != "production":
            return self

        for field_name in type(self).model_fields:
            if not self._field_is_sensitive(field_name):
                continue
            value = getattr(self, field_name, None)
            if isinstance(value, str) and value.strip().lower() in INSECURE_DEFAULT_VALUES:
                raise ValueError(
                    f"[Security] Field '{field_name}' has an insecure default "
                    f"value in production: {value!r}. "
                    "Override with a strong value via .env.local or environment variable."
                )
        return self

    # ── CLI args generation ──────────────────────────────────────────

    def to_command_args(self, args_prefix: str = "--") -> list[str]:
        """Convert configured fields into CLI-style argument pairs.

        Example: ``my_field=42`` produces ``["--my-field", "42"]``.
        Boolean ``True`` values emit only the flag name. ``None`` values
        are skipped.

        Args:
            args_prefix: Prefix for argument names (default ``"--"``).

        Returns:
            Flat list of CLI argument tokens.
        """
        args: list[str] = []
        for field_name in type(self).model_fields:
            value = getattr(self, field_name, None)
            if value is None:
                continue
            arg_name = f"{args_prefix}{field_name.replace('_', '-')}"
            if isinstance(value, bool):
                if value:
                    args.append(arg_name)
            else:
                args.extend([arg_name, str(value)])
        return args

    # ── Parameter metadata ───────────────────────────────────────────

    def get_parameter_descriptions(self) -> list[dict[str, Any]]:
        """Return field metadata for documentation and introspection.

        Each entry includes the field name, type annotation, default
        value, description, required flag, fixed tag, and custom tags.

        Returns:
            List of metadata dicts with keys: ``name``, ``type``,
            ``default``, ``description``, ``required``, ``fixed``,
            ``tags``.
        """
        result: list[dict[str, Any]] = []
        for field_name, field_info in type(self).model_fields.items():
            extra: dict[str, Any] = getattr(field_info, "json_schema_extra", None) or {}
            result.append(
                {
                    "name": field_name,
                    "type": field_info.annotation,
                    "default": field_info.default,
                    "description": field_info.description,
                    "required": field_info.is_required(),
                    "fixed": extra.get("fixed", False),
                    "tags": extra.get("tags", []),
                }
            )
        return result

    # ── Field factory ────────────────────────────────────────────────

    @classmethod
    def field(
        cls,
        default: Any = ...,
        *,
        description: str | None = None,
        tags: list[str] | None = None,
        fixed: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Create a ``pydantic.FieldInfo`` with metadata in ``json_schema_extra``.

        This is a convenience factory around ``pydantic.Field()`` that
        stores custom metadata (``tags``, ``fixed``) in
        ``json_schema_extra`` rather than requiring a custom Field
        subclass.

        Args:
            default: Default value (``...`` for required fields).
            description: Human-readable field description.
            tags: Optional list of semantic tags (e.g. ``["advanced"]``).
            fixed: When True, ``update_from()`` will skip this field.
            **kwargs: Additional ``pydantic.Field()`` arguments forwarded
                directly.

        Returns:
            A ``FieldInfo`` instance for use in model field declarations.

        Examples:
            >>> class MyParams(BaseParameters):
            ...     api_url: str = BaseParameters.field(
            ...         "http://localhost:8080",
            ...         description="Backend API URL",
            ...         tags=["network"],
            ...     )
            ...     seed: int = BaseParameters.field(
            ...         42,
            ...         description="Random seed",
            ...         fixed=True,
            ...     )
        """
        extra: dict[str, Any] = kwargs.pop("json_schema_extra", {}) or {}
        if description is not None:
            kwargs["description"] = description
        if fixed:
            extra["fixed"] = True
        if tags:
            extra["tags"] = tags
        if extra:
            kwargs["json_schema_extra"] = extra
        return Field(default=default, **kwargs)


__all__ = [
    "BaseParameters",
    "ENV_VAR_PATTERN",
    "SENSITIVE_SUBSTRINGS",
    "INSECURE_DEFAULT_VALUES",
    "is_sensitive_field",
    "mask_value",
]
