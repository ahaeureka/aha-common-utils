"""Tests for ConfigStore dotenv vs process environment precedence.

Validates the required contracts:
1. Base .env is loaded for local dotenv defaults
2. .env.local overrides base .env
3. Environment-specific dotenv overrides base dotenv
4. Pre-existing process key beats all dotenv files
5. Pre-existing empty-string process key is also restored
6. Unrelated process key is left unchanged
"""

from pathlib import Path
from typing import Any, cast

import pytest
from aha_common_utils.config_base import BaseParameters
from aha_common_utils.config_store import ConfigStore
from loguru import logger as _loguru_logger


class ExampleConfig(BaseParameters):
    """Minimal config model for testing — no know-know types or fields."""

    EXAMPLE_VALUE: str = "default"


def _write_env_placeholder_config(base_dir: Path) -> None:
    """Write a minimal TOML config that reads EXAMPLE_VALUE from dotenv/process env."""
    (base_dir / "config.toml").write_text('EXAMPLE_VALUE = "${env:EXAMPLE_VALUE:-default}"\n', encoding="utf-8")


def _example_value(cfg: BaseParameters) -> str:
    """Return the dynamically generated config field for pyright-friendly tests."""

    return cast(str, cast(Any, cfg).EXAMPLE_VALUE)


# ── Contract 1: base .env is loaded ──────────────────────────────────────


def test_base_dotenv_is_loaded(tmp_path: Path, monkeypatch) -> None:
    """A project-root .env file provides local dotenv defaults."""
    _write_env_placeholder_config(tmp_path)
    (tmp_path / ".env").write_text("EXAMPLE_VALUE=base-env\n", encoding="utf-8")

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("EXAMPLE_VALUE", raising=False)

    store = ConfigStore()
    cfg = store.load(ExampleConfig, base_dir=tmp_path)

    assert _example_value(cfg) == "base-env"


# ── Contract 2: .env.local overrides base .env ───────────────────────────


def test_env_local_overrides_base_dotenv(tmp_path: Path, monkeypatch) -> None:
    """.env.local values win over lower-priority .env values."""
    _write_env_placeholder_config(tmp_path)
    (tmp_path / ".env").write_text("EXAMPLE_VALUE=base-env\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("EXAMPLE_VALUE=local-dotenv\n", encoding="utf-8")

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("EXAMPLE_VALUE", raising=False)

    store = ConfigStore()
    cfg = store.load(ExampleConfig, base_dir=tmp_path)

    assert _example_value(cfg) == "local-dotenv"


# ── Contract 3: env-specific dotenv overrides base dotenv ────────────────


def test_environment_local_dotenv_overrides_base_dotenv(tmp_path: Path, monkeypatch) -> None:
    """.env.<ENV>.local values win over .env.local when both define the same key."""
    _write_env_placeholder_config(tmp_path)
    (tmp_path / ".env.local").write_text("EXAMPLE_VALUE=base-dotenv\n", encoding="utf-8")
    (tmp_path / ".env.test.local").write_text("EXAMPLE_VALUE=env-specific-dotenv\n", encoding="utf-8")

    monkeypatch.setenv("APP_ENV", "test")
    # Ensure no pre-existing process value for the test key
    monkeypatch.delenv("EXAMPLE_VALUE", raising=False)

    store = ConfigStore()
    cfg = store.load(ExampleConfig, base_dir=tmp_path)

    assert _example_value(cfg) == "env-specific-dotenv"


# ── Contract 4: pre-existing process key beats all dotenv files ──────────


def test_process_env_beats_dotenv_files(tmp_path: Path, monkeypatch) -> None:
    """A process env value set before load() is never overwritten by dotenv."""
    _write_env_placeholder_config(tmp_path)
    (tmp_path / ".env.local").write_text("EXAMPLE_VALUE=base-dotenv\n", encoding="utf-8")
    (tmp_path / ".env.test.local").write_text("EXAMPLE_VALUE=env-specific-dotenv\n", encoding="utf-8")

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("EXAMPLE_VALUE", "process-wins")

    store = ConfigStore()
    cfg = store.load(ExampleConfig, base_dir=tmp_path)

    assert _example_value(cfg) == "process-wins"


# ── Contract 5: pre-existing empty string is restored ────────────────────


def test_process_empty_string_is_restored_after_dotenv(tmp_path: Path, monkeypatch) -> None:
    """A pre-existing empty string in process env is restored after dotenv loading."""
    _write_env_placeholder_config(tmp_path)
    (tmp_path / ".env.local").write_text("EXAMPLE_VALUE=dotenv-value\n", encoding="utf-8")

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("EXAMPLE_VALUE", "")

    store = ConfigStore()
    cfg = store.load(ExampleConfig, base_dir=tmp_path)

    # Empty string is an explicit value — the field schema decides validity
    assert _example_value(cfg) == ""


# ── Contract 6: unrelated process key is left unchanged ──────────────────


def test_unrelated_process_key_preserved(tmp_path: Path, monkeypatch) -> None:
    """Process env keys not in any dotenv file are preserved unchanged."""
    _write_env_placeholder_config(tmp_path)
    (tmp_path / ".env.local").write_text("EXAMPLE_VALUE=dotenv\n", encoding="utf-8")

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("UNRELATED_VAR", "keep-me")

    store = ConfigStore()
    store.load(ExampleConfig, base_dir=tmp_path)

    # After load, the unrelated process key must still be in os.environ
    import os

    assert os.environ.get("UNRELATED_VAR") == "keep-me"


# ── Guard 1: process-env prefix discipline (opt-in) ───────────────────────


class DatabaseParameters(BaseParameters):
    """Nested group mirroring a TOML ``[database]`` section."""

    url: str = "default-url"


class AppParameters(BaseParameters):
    """Nested group mirroring a TOML ``[app]`` section."""

    value: str = ""
    debug: bool = False


class LlmParameters(BaseParameters):
    """Nested group whose own field names contain underscores."""

    api_key: str = ""
    base_url: str = ""


class NestedConfig(BaseParameters):
    """Nested-group config model mirroring the k2skills shape."""

    app: AppParameters = AppParameters()
    database: DatabaseParameters = DatabaseParameters()
    llm: LlmParameters = LlmParameters()


def _write_nested_config(base_dir: Path, body: str = '[database]\nurl = "from-file"\n') -> None:
    """Write a nested-section TOML config."""
    (base_dir / "config.toml").write_text(body, encoding="utf-8")


def _database_url(cfg: BaseParameters) -> str:
    """Return the nested ``database.url`` value for pyright-friendly tests."""
    return cast(str, cast(Any, cfg).database.url)


def _app_value(cfg: BaseParameters) -> str:
    """Return the nested ``app.value`` value for pyright-friendly tests."""
    return cast(str, cast(Any, cfg).app.value)


def test_bare_env_key_is_ignored_when_reject_bare_env(tmp_path: Path, monkeypatch) -> None:
    """With ``reject_bare_env`` a bare ``DATABASE_URL`` must not reach ``database.url``."""
    _write_nested_config(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "from-bare-env")

    cfg = ConfigStore().load(NestedConfig, base_dir=tmp_path, reject_bare_env=True, env_prefix="QUNAPAI_")

    assert _database_url(cfg) == "from-file"


def test_prefixed_env_key_applies_when_reject_bare_env(tmp_path: Path, monkeypatch) -> None:
    """The prefixed form still overrides when ``reject_bare_env`` is on."""
    _write_nested_config(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "from-bare-env")
    monkeypatch.setenv("QUNAPAI_DATABASE_URL", "from-prefixed-env")

    cfg = ConfigStore().load(NestedConfig, base_dir=tmp_path, reject_bare_env=True, env_prefix="QUNAPAI_")

    assert _database_url(cfg) == "from-prefixed-env"


def test_bare_env_key_applies_by_default(tmp_path: Path, monkeypatch) -> None:
    """Default stays permissive so existing consumers (k2skills) are unaffected."""
    _write_nested_config(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "from-bare-env")

    cfg = ConfigStore().load(NestedConfig, base_dir=tmp_path)

    assert _database_url(cfg) == "from-bare-env"


def test_reject_bare_env_requires_a_prefix(tmp_path: Path) -> None:
    """``reject_bare_env`` without ``env_prefix`` would accept nothing — fail fast."""
    _write_nested_config(tmp_path)

    with pytest.raises(ValueError):
        ConfigStore().load(NestedConfig, base_dir=tmp_path, reject_bare_env=True)


# ── Guard 2: unknown config keys ─────────────────────────────────────────


def test_unknown_keys_reports_misspelled_file_key(tmp_path: Path, monkeypatch) -> None:
    """A misspelled TOML key is reported instead of silently ignored."""
    _write_nested_config(tmp_path, '[database]\nurll = "typo"\n')
    monkeypatch.setenv("APP_ENV", "test")

    store = ConfigStore()
    store.load(NestedConfig, base_dir=tmp_path)

    assert store.unknown_keys == ("database.urll",)


def test_unknown_keys_ignores_unrelated_process_env(tmp_path: Path, monkeypatch) -> None:
    """Arbitrary process env keys must not pollute the unknown-key report."""
    _write_nested_config(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SOME_OTHER_APP_DEBUG", "1")
    monkeypatch.setenv("TOTALLY_UNRELATED", "x")

    store = ConfigStore()
    store.load(NestedConfig, base_dir=tmp_path)

    assert store.unknown_keys == ()


def test_unknown_keys_empty_before_load() -> None:
    """The report is empty until a load has happened."""
    assert ConfigStore().unknown_keys == ()


# ── Guard 3: unresolved ${env:...} placeholders ───────────────────────────


def test_unresolved_placeholder_reported_and_value_kept_literal(tmp_path: Path, monkeypatch) -> None:
    """An unset placeholder is reported; the literal is preserved (semantics unchanged).

    Uses ``[app] value`` rather than the flat ``EXAMPLE_VALUE`` field: the dotenv
    tests above leave their own ``EXAMPLE_VALUE`` behind in ``os.environ``
    (``_load_env_files`` restores pre-existing keys but keeps the ones dotenv
    added), so a colliding key would be overwritten by that leak.
    """
    (tmp_path / "config.toml").write_text('[app]\nvalue = "${env:NO_SUCH_VAR}"\n', encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("NO_SUCH_VAR", raising=False)

    store = ConfigStore()
    cfg = store.load(NestedConfig, base_dir=tmp_path)

    assert store.unresolved_placeholders == ("NO_SUCH_VAR",)
    assert _app_value(cfg) == "${env:NO_SUCH_VAR}"


def test_resolved_placeholder_not_reported(tmp_path: Path, monkeypatch) -> None:
    """A ``:-default`` fallback counts as resolved."""
    (tmp_path / "config.toml").write_text('[app]\nvalue = "${env:NO_SUCH_VAR:-fallback}"\n', encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("NO_SUCH_VAR", raising=False)

    store = ConfigStore()
    cfg = store.load(NestedConfig, base_dir=tmp_path)

    assert store.unresolved_placeholders == ()
    assert _app_value(cfg) == "fallback"


def test_unresolved_placeholders_empty_before_load() -> None:
    """The report is empty until a load has happened."""
    assert ConfigStore().unresolved_placeholders == ()


# ── Warning switches (default off) ───────────────────────────────────────


def test_warn_flags_emit_logging_warnings(tmp_path: Path, monkeypatch) -> None:
    """Both opt-in warnings fire when explicitly enabled."""
    (tmp_path / "config.toml").write_text(
        '[database]\nurll = "typo"\n\n[app]\nvalue = "${env:NO_SUCH_VAR}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("NO_SUCH_VAR", raising=False)

    messages: list[str] = []
    sink_id = _loguru_logger.add(lambda message: messages.append(message), level="WARNING")
    try:
        ConfigStore().load(
            NestedConfig,
            base_dir=tmp_path,
            warn_unknown_keys=True,
            warn_unresolved_placeholders=True,
        )
    finally:
        _loguru_logger.remove(sink_id)

    joined = "\n".join(str(message) for message in messages)
    assert "database.urll" in joined
    assert "NO_SUCH_VAR" in joined


def test_warn_flags_off_by_default(tmp_path: Path, monkeypatch) -> None:
    """Default load stays silent, but the reports are still populated."""
    (tmp_path / "config.toml").write_text(
        '[database]\nurll = "typo"\n\n[app]\nvalue = "${env:NO_SUCH_VAR}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("NO_SUCH_VAR", raising=False)

    messages: list[str] = []
    sink_id = _loguru_logger.add(lambda message: messages.append(message), level="WARNING")
    try:
        store = ConfigStore()
        store.load(NestedConfig, base_dir=tmp_path)
    finally:
        _loguru_logger.remove(sink_id)

    joined = "\n".join(str(message) for message in messages)
    assert "database.urll" not in joined
    assert store.unknown_keys == ("database.urll",)
    assert store.unresolved_placeholders == ("NO_SUCH_VAR",)


# ── Parity requirements for the qunapai migration (AC-10 value equality) ─


def test_prefixed_env_key_match_is_case_insensitive(tmp_path: Path, monkeypatch) -> None:
    """A lowercase prefix spelling must still be adopted.

    Process env names are conventionally written in any case, and a consumer
    that declares a prefix should not silently ignore ``qunapai_database_url``.
    """
    _write_nested_config(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("qunapai_database_url", "from-lowercase-prefix")

    cfg = ConfigStore().load(NestedConfig, base_dir=tmp_path, reject_bare_env=True, env_prefix="QUNAPAI_")

    assert _database_url(cfg) == "from-lowercase-prefix"


def test_dotenv_bare_key_applies_even_with_reject_bare_env(tmp_path: Path, monkeypatch) -> None:
    """A bare key supplied by a dotenv file is still adopted.

    ``reject_bare_env`` guards against *unrelated container variables*; the
    dotenv chain is controlled by the project itself, so its keys carry the
    same authority as prefixed process-environment keys.
    """
    _write_nested_config(tmp_path)
    (tmp_path / ".env.local").write_text("DATABASE_URL=from-dotenv\n", encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    cfg = ConfigStore().load(NestedConfig, base_dir=tmp_path, reject_bare_env=True, env_prefix="QUNAPAI_")

    assert _database_url(cfg) == "from-dotenv"


def test_bare_process_env_key_still_rejected_when_dotenv_defined_one(tmp_path: Path, monkeypatch) -> None:
    """The dotenv exemption must not widen the bare-name rule for process env."""
    _write_nested_config(tmp_path)
    (tmp_path / ".env.local").write_text("SOMETHING_ELSE=x\n", encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "from-bare-env")

    cfg = ConfigStore().load(NestedConfig, base_dir=tmp_path, reject_bare_env=True, env_prefix="QUNAPAI_")

    assert _database_url(cfg) == "from-file"


def test_blank_unresolved_placeholders_replaces_literal_with_empty(tmp_path: Path, monkeypatch) -> None:
    """Opt-in: an unresolved placeholder becomes an empty string instead of a literal."""
    (tmp_path / "config.toml").write_text('[app]\nvalue = "${env:NO_SUCH_VAR}"\n', encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("NO_SUCH_VAR", raising=False)

    store = ConfigStore()
    cfg = store.load(NestedConfig, base_dir=tmp_path, blank_unresolved_placeholders=True)

    assert _app_value(cfg) == ""
    assert store.unresolved_placeholders == ("NO_SUCH_VAR",)


def test_invalid_bool_env_value_names_the_variable(tmp_path: Path, monkeypatch) -> None:
    """A bad typed value must fail loudly and name the variable it came from."""
    _write_nested_config(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("QUNAPAI_APP_DEBUG", "not-a-bool")

    with pytest.raises(ValueError, match="QUNAPAI_APP_DEBUG"):
        ConfigStore().load(NestedConfig, base_dir=tmp_path, reject_bare_env=True, env_prefix="QUNAPAI_")


# ── The naming rule itself ───────────────────────────────────────────────


def test_env_name_is_derived_from_scope_and_key(tmp_path: Path, monkeypatch) -> None:
    """``llm.api_key`` must read ``LLM_API_KEY`` — the case greedy splitting broke.

    Field names contain underscores, so a name cannot be split back into path
    segments. The index is built *from the model* instead, which inverts the
    derivation exactly.
    """
    _write_nested_config(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("QUNAPAI_LLM_API_KEY", "sk-derived")
    monkeypatch.setenv("QUNAPAI_LLM_BASE_URL", "https://llm.example/v1")

    cfg = ConfigStore().load(NestedConfig, base_dir=tmp_path, reject_bare_env=True, env_prefix="QUNAPAI_")

    assert cast(Any, cfg).llm.api_key == "sk-derived"
    assert cast(Any, cfg).llm.base_url == "https://llm.example/v1"


def test_unknown_env_key_is_reported_not_guessed(tmp_path: Path, monkeypatch) -> None:
    """A name matching no field path is reported, not turned into a dead table."""
    _write_nested_config(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("QUNAPAI_TOTALLY_MADE_UP", "x")

    store = ConfigStore()
    cfg = store.load(NestedConfig, base_dir=tmp_path, reject_bare_env=True, env_prefix="QUNAPAI_")

    assert store.unknown_env_keys == ("QUNAPAI_TOTALLY_MADE_UP",)
    assert not hasattr(cast(Any, cfg), "totally")
    assert _database_url(cfg) == "from-file"
