"""Tests for ConfigStore dotenv vs process environment precedence.

Validates the four required contracts:
1. Environment-specific dotenv overrides base dotenv
2. Pre-existing process key beats both dotenv files
3. Pre-existing empty-string process key is also restored
4. Unrelated process key is left unchanged
"""

from pathlib import Path

from aha_common_utils.config_base import BaseParameters
from aha_common_utils.config_store import ConfigStore


class ExampleConfig(BaseParameters):
    """Minimal config model for testing — no know-know types or fields."""

    EXAMPLE_VALUE: str = "default"


# ── Contract 1: env-specific dotenv overrides base dotenv ────────────────

def test_environment_local_dotenv_overrides_base_dotenv(tmp_path: Path, monkeypatch) -> None:
    """.env.<ENV>.local values win over .env.local when both define the same key."""
    (tmp_path / ".env.local").write_text("EXAMPLE_VALUE=base-dotenv\n", encoding="utf-8")
    (tmp_path / ".env.test.local").write_text("EXAMPLE_VALUE=env-specific-dotenv\n", encoding="utf-8")

    monkeypatch.setenv("APP_ENV", "test")
    # Ensure no pre-existing process value for the test key
    monkeypatch.delenv("EXAMPLE_VALUE", raising=False)

    store = ConfigStore()
    cfg = store.load(ExampleConfig, base_dir=tmp_path)

    assert cfg.EXAMPLE_VALUE == "env-specific-dotenv"


# ── Contract 2: pre-existing process key beats both dotenv files ─────────

def test_process_env_beats_dotenv_files(tmp_path: Path, monkeypatch) -> None:
    """A process env value set before load() is never overwritten by dotenv."""
    (tmp_path / ".env.local").write_text("EXAMPLE_VALUE=base-dotenv\n", encoding="utf-8")
    (tmp_path / ".env.test.local").write_text("EXAMPLE_VALUE=env-specific-dotenv\n", encoding="utf-8")

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("EXAMPLE_VALUE", "process-wins")

    store = ConfigStore()
    cfg = store.load(ExampleConfig, base_dir=tmp_path)

    assert cfg.EXAMPLE_VALUE == "process-wins"


# ── Contract 3: pre-existing empty string is restored ────────────────────

def test_process_empty_string_is_restored_after_dotenv(tmp_path: Path, monkeypatch) -> None:
    """A pre-existing empty string in process env is restored after dotenv loading."""
    (tmp_path / ".env.local").write_text("EXAMPLE_VALUE=dotenv-value\n", encoding="utf-8")

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("EXAMPLE_VALUE", "")

    store = ConfigStore()
    cfg = store.load(ExampleConfig, base_dir=tmp_path)

    # Empty string is an explicit value — the field schema decides validity
    assert cfg.EXAMPLE_VALUE == ""


# ── Contract 4: unrelated process key is left unchanged ──────────────────

def test_unrelated_process_key_preserved(tmp_path: Path, monkeypatch) -> None:
    """Process env keys not in any dotenv file are preserved unchanged."""
    (tmp_path / ".env.local").write_text("EXAMPLE_VALUE=dotenv\n", encoding="utf-8")

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("UNRELATED_VAR", "keep-me")

    store = ConfigStore()
    store.load(ExampleConfig, base_dir=tmp_path)

    # After load, the unrelated process key must still be in os.environ
    import os

    assert os.environ.get("UNRELATED_VAR") == "keep-me"
