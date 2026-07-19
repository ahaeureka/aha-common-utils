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

from aha_common_utils.config_base import BaseParameters
from aha_common_utils.config_store import ConfigStore


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
