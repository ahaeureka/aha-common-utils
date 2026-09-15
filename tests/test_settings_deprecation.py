"""`SecureBaseSettings` 的弃用行为：必须响亮失败，而不是静默退化成一个坏基类。"""

from __future__ import annotations

import importlib
import os
import warnings

import pytest
from aha_common_utils import settings as settings_module
from aha_common_utils.config_base import BaseParameters


def test_attribute_access_warns_and_returns_base_parameters() -> None:
    with pytest.warns(DeprecationWarning, match="SecureBaseSettings 已被移除"):
        resolved = settings_module.SecureBaseSettings

    assert resolved is BaseParameters


def test_from_import_warns() -> None:
    """`from aha_common_utils.settings import SecureBaseSettings` 也必须发出告警。"""
    with pytest.warns(DeprecationWarning, match="不会读取环境变量或 dotenv"):
        module = importlib.import_module("aha_common_utils.settings")
        legacy = module.SecureBaseSettings

    assert legacy is BaseParameters


def test_legacy_base_class_really_ignores_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """告警文字描述的陷阱必须真实存在：继承它 + 配置 env_prefix ⇒ 环境变量被忽略。"""
    from pydantic_settings import SettingsConfigDict

    monkeypatch.setenv("QUNAPAI_PROBE_VALUE", "from-env")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)

        class LegacySettings(settings_module.SecureBaseSettings):  # type: ignore[misc]
            model_config = SettingsConfigDict(env_prefix="QUNAPAI_")

            PROBE_VALUE: str = "default"

    assert LegacySettings().PROBE_VALUE == "default"
    assert os.environ["QUNAPAI_PROBE_VALUE"] == "from-env"


def test_unknown_attribute_still_raises() -> None:
    with pytest.raises(AttributeError):
        _ = settings_module.does_not_exist


def test_deprecated_name_is_not_star_exported() -> None:
    assert "SecureBaseSettings" not in settings_module.__all__
