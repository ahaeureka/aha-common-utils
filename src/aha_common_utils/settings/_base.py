"""SecureBaseSettings — 安全分层配置基类。

加载优先级（从低→高）：
  1. 代码默认值
  2. config.yaml / config.yml    （非敏感基础配置，可提交版本库）
  3. config.<APP_ENV>.yaml/yml   （环境专属非敏感覆盖，可提交版本库）
  4. config.toml                  （非敏感基础配置，可提交版本库）
  5. config.<APP_ENV>.toml        （环境专属非敏感覆盖，可提交版本库）
  6. .env.local                   （⚠️ 仅存放敏感值，已 .gitignore）
  7. 进程环境变量                 （最高优先级，容器/CI 注入）
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar, Set

from pydantic import model_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
    YamlConfigSettingsSource,
)

from ._constants import INSECURE_DEFAULT_VALUES, is_sensitive_field, mask_value
from ._discovery import build_sensitive_env_file, build_toml_config_files, build_yaml_config_files

__all__ = ["SecureBaseSettings"]


class SecureBaseSettings(BaseSettings):
    """安全分层配置基类。

    所有需要分层配置加载的 Settings 类应继承此基类，而非直接继承
    ``pydantic_settings.BaseSettings``。

    功能：
    1. **分层 TOML + env 加载**：自动按
       ``config.toml`` → ``config.<APP_ENV>.toml`` → ``.env.local`` → 进程环境变量
       顺序加载，优先级依次升高。
    2. **敏感字段屏蔽**：在 ``__repr__`` / ``__str__`` / ``safe_dump()`` 中，
       名称含 password、secret、api_key 等关键词的字段值会被替换为 ``xxxx****``。
    3. **生产安全校验**：当 ``APP_ENV=production`` 时，自动检测敏感字段是否仍为
       已知不安全的默认值，若是则在应用启动时立即抛出 ``ValueError``。

    子类可通过 ``_EXTRA_SENSITIVE_FIELDS`` 追加特定字段名（精确匹配，忽略大小写）：

    Examples:
        >>> from aha_common_utils.settings import SecureBaseSettings
        >>> from pydantic_settings import SettingsConfigDict

        >>> class AppSettings(SecureBaseSettings):
        ...     model_config = SettingsConfigDict(env_prefix="MYAPP_")
        ...     DATABASE_URL: str = "postgresql+asyncpg://localhost/dev"
        ...     SECRET_KEY: str = "change-me-in-production"
        ...     LLM_API_KEY: str = ""

        >>> settings = AppSettings()
        >>> print(settings)   # SECRET_KEY 和 LLM_API_KEY 会被屏蔽
    """

    # 子类可追加需要屏蔽的额外字段名（精确匹配，忽略大小写）
    _EXTRA_SENSITIVE_FIELDS: ClassVar[Set[str]] = set()

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # 分层加载：覆盖 settings_customise_sources
    # ------------------------------------------------------------------

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,  # noqa: ARG003 (replaced)
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """用 TOML + YAML + .env.local 替换默认 dotenv，按优先级从高→低排列。

        优先级（tuple 中靠前 = 优先级更高）：
          init_settings
          > env_settings          （进程环境变量，容器/CI 注入敏感值）
          > dotenv_local          （.env.local，个人本地敏感值，已 .gitignore）
          > toml_env              （config.<APP_ENV>.toml，环境专属非敏感覆盖）
          > toml_base             （config.toml，基础非敏感默认值）
          > yaml_env              （config.<APP_ENV>.yaml/yml，环境专属非敏感覆盖）
          > yaml_base             （config.yaml/yml，基础非敏感默认值）
          > file_secret_settings
        """
        model_cfg = settings_cls.model_config
        enc = model_cfg.get("env_file_encoding", "utf-8")

        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]

        # ── .env.local（仅敏感值，已 .gitignore） ──────────────────────────
        env_local = build_sensitive_env_file()
        if env_local:
            sources.append(
                DotEnvSettingsSource(
                    settings_cls,
                    env_file=str(env_local),
                    env_file_encoding=enc,
                )
            )

        # ── TOML 配置文件（非敏感，可提交版本库） ──────────────────────────
        # 子类可在 model_config 中手动指定 toml_file 跳过自动探测
        explicit_toml: str | None = model_cfg.get("toml_file")  # type: ignore[assignment]
        if explicit_toml:
            toml_path = Path(explicit_toml)
            if toml_path.is_file():
                sources.append(TomlConfigSettingsSource(settings_cls, toml_file=toml_path))
        else:
            # 按优先级从高→低追加：先 config.<APP_ENV>.toml，再 config.toml
            for toml_path in reversed(build_toml_config_files()):
                sources.append(
                    TomlConfigSettingsSource(settings_cls, toml_file=toml_path)
                )

        # ── YAML 配置文件（非敏感，可提交版本库） ──────────────────────────
        # 子类可在 model_config 中手动指定 yaml_file 跳过自动探测
        explicit_yaml: str | None = model_cfg.get("yaml_file")  # type: ignore[assignment]
        if explicit_yaml:
            yaml_path = Path(explicit_yaml)
            if yaml_path.is_file():
                sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=yaml_path))
        else:
            # 按优先级从高→低追加：先 config.<APP_ENV>.yaml，再 config.yaml
            for yaml_path in reversed(build_yaml_config_files()):
                sources.append(
                    YamlConfigSettingsSource(settings_cls, yaml_file=yaml_path)
                )

        sources.append(file_secret_settings)
        return tuple(sources)

    # ------------------------------------------------------------------
    # 生产安全校验
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def _check_production_security(self) -> "SecureBaseSettings":
        """生产环境启动时检测敏感字段中的不安全默认值。

        仅在 ``APP_ENV=production`` 时生效，避免在开发/测试环境误报。
        抛出 ValueError 使应用在启动阶段快速失败，而非运行时泄露默认值。
        """
        app_env = os.environ.get("APP_ENV", "development").strip().lower()
        if app_env != "production":
            return self

        for field_name in self.model_fields:
            if not self._field_is_sensitive(field_name):
                continue
            value = getattr(self, field_name, None)
            if isinstance(value, str) and value.strip().lower() in INSECURE_DEFAULT_VALUES:
                raise ValueError(
                    f"[Security] 生产环境中字段 '{field_name}' 使用了不安全的默认值: {value!r}。"
                    "请在 .env.local 或进程环境变量中覆盖为强值。"
                )
        return self

    # ------------------------------------------------------------------
    # 安全 repr / safe_dump（屏蔽敏感字段）
    # ------------------------------------------------------------------

    def _field_is_sensitive(self, field_name: str) -> bool:
        """判断指定字段是否为敏感字段（综合名称模式 + 子类追加列表）。"""
        return is_sensitive_field(field_name) or field_name.lower() in {
            f.lower() for f in self._EXTRA_SENSITIVE_FIELDS
        }

    def __repr__(self) -> str:
        """屏蔽敏感字段的安全 repr，防止密钥意外出现在日志中。"""
        parts: list[str] = []
        for field_name in self.model_fields:
            value = getattr(self, field_name, None)
            if self._field_is_sensitive(field_name) and value:
                parts.append(f"{field_name}={mask_value(value)}")
            else:
                parts.append(f"{field_name}={value!r}")
        return f"{self.__class__.__name__}({', '.join(parts)})"

    def __str__(self) -> str:
        return self.__repr__()

    def safe_dump(self) -> dict[str, Any]:
        """返回屏蔽了敏感字段的配置字典，适合在日志或诊断端点中输出。

        Returns:
            字段名 → 安全表示值 的字典（敏感字段已被 mask_value() 屏蔽）。

        Examples:
            >>> settings.safe_dump()
            {'APP_ENV': 'development', 'DATABASE_URL': 'post****', ...}
        """
        result: dict[str, Any] = {}
        for field_name in self.model_fields:
            value = getattr(self, field_name, None)
            if self._field_is_sensitive(field_name) and value:
                result[field_name] = mask_value(value)
            else:
                result[field_name] = value
        return result
