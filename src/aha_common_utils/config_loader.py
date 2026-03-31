"""统一配置加载器

负责加载配置文件、环境变量，并实例化已注册的配置类。
与具体配置项解耦，只负责加载和组装配置。
"""

from pathlib import Path
from typing import Any, Dict, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

from .config_registry import get_main_config_class, get_registry
from .logging import get_logger
from .path_utils import find_env_files_recursive

logger = get_logger(__name__)


class ConfigLoader:
    """统一配置加载器

    负责：
    1. 加载 .env 文件（支持递归）
    2. 加载 TOML/YAML/JSON 配置文件
    3. 实例化已注册的配置类
    4. 与具体配置项解耦

    Examples:
        >>> # 方式1: 使用默认递归加载
        >>> loader = ConfigLoader()
        >>> settings = loader.load()

        >>> # 方式2: 指定配置文件
        >>> loader = ConfigLoader(env_file="/app/.env.prod", toml_file="/app/config.toml")
        >>> settings = loader.load(recursive_env=False)

        >>> # 方式3: 从指定目录递归加载
        >>> loader = ConfigLoader()
        >>> settings = loader.load(start_path=Path("/app/packages/distill-ai"))
    """

    def __init__(
        self,
        env_file: Optional[str | Path] = None,
        toml_file: Optional[str | Path] = None,
        yaml_file: Optional[str | Path] = None,
        json_file: Optional[str | Path] = None,
        provider_modules: Optional[list[str]] = None,
    ):
        """初始化配置加载器

        Args:
            env_file: .env 文件路径（指定后将禁用递归查找）
            toml_file: TOML 配置文件路径
            yaml_file: YAML 配置文件路径
            json_file: JSON 配置文件路径
            provider_modules: 需要导入的 provider 模块列表，None 则自动扫描
        """
        self.env_file = env_file
        self.toml_file = toml_file
        self.yaml_file = yaml_file
        self.json_file = json_file
        self.provider_modules = provider_modules
        self._registry = get_registry()

    def load(
        self,
        recursive_env: bool = True,
        start_path: Optional[Path] = None,
        config_overrides: Optional[Dict[str, Any]] = None,
        auto_generate: bool = True,
    ) -> BaseSettings:
        """加载并实例化主配置

        Args:
            recursive_env: 是否递归查找 .env 文件（从根目录到当前目录）
            start_path: 递归查找的起始路径，默认为当前工作目录
            config_overrides: 配置覆盖值（用于运行时覆盖）
            auto_generate: 如果没有主配置，是否自动生成（默认 True）

        Returns:
            已实例化的主配置对象

        Raises:
            ValueError: 如果没有注册主配置且 auto_generate=False

        Examples:
            >>> loader = ConfigLoader()
            >>> settings = loader.load()  # 自动生成主配置
            >>> settings = loader.load(recursive_env=False)  # 禁用递归
            >>> settings = loader.load(config_overrides={"app_name": "test"})  # 覆盖配置
        """
        # 检查是否注册了主配置
        main_config_class = get_main_config_class()
        if main_config_class is None:
            if not auto_generate:
                raise ValueError(
                    "没有注册主配置。请使用 @register_config(name='app', is_main=True) "
                    "装饰器注册主配置类，或启用 auto_generate=True 自动生成。"
                )
            # 触发 provider 导入（确保所有装饰器被执行）
            self._ensure_providers_imported(self.provider_modules)
            # 自动生成主配置
            main_config_class = self._generate_main_config()

        # 构建配置字典
        config_dict = self._build_config_dict(recursive_env, start_path)

        # 从配置文件加载数据
        file_data = self._load_file_data()

        # 动态创建配置类
        class DynamicMainSettings(main_config_class):  # type: ignore
            model_config = SettingsConfigDict(**config_dict)  # type: ignore[misc]

        # 实例化配置（合并文件数据和覆盖）
        init_data = {**(file_data or {}), **(config_overrides or {})}
        return DynamicMainSettings(**init_data)

    def load_specific(
        self,
        config_name: str,
        recursive_env: bool = True,
        start_path: Optional[Path] = None,
        config_overrides: Optional[Dict[str, Any]] = None,
    ) -> BaseSettings:
        """加载并实例化指定的配置类

        Args:
            config_name: 配置名称（已注册的配置）
            recursive_env: 是否递归查找 .env 文件
            start_path: 递归查找的起始路径
            config_overrides: 配置覆盖值

        Returns:
            已实例化的配置对象

        Raises:
            ValueError: 如果配置未注册

        Examples:
            >>> loader = ConfigLoader()
            >>> llm_settings = loader.load_specific("llm")
            >>> db_settings = loader.load_specific("database")
        """
        config_class = self._registry.get_config(config_name)
        if config_class is None:
            raise ValueError(
                f"配置 '{config_name}' 未注册。请使用 @register_config(name='{config_name}') 装饰器注册配置类。"
            )

        # 构建配置字典
        config_dict = self._build_config_dict(recursive_env, start_path)

        # 动态创建配置类
        class DynamicSettings(config_class):  # type: ignore
            model_config = SettingsConfigDict(**config_dict)

        # 实例化配置
        if config_overrides:
            return DynamicSettings(**config_overrides)
        return DynamicSettings()

    def _ensure_providers_imported(self, modules: Optional[list[str]] = None):
        """确保所有 provider 被导入（触发装饰器执行）

        Args:
            modules: 需要导入的模块列表，None 则自动扫描
        """
        import importlib
        import pkgutil

        if modules is not None:
            # 使用指定的模块列表
            for module_name in modules:
                try:
                    importlib.import_module(module_name)
                    logger.debug(f"Imported {module_name}")
                except Exception as e:
                    logger.debug(f"Skip importing {module_name}: {e}")
            return

        # 自动扫描模式
        packages_to_scan = ["distill_dao", "distill_ai", "distill_etl"]
        scanned_modules = set()

        for package_name in packages_to_scan:
            try:
                package = importlib.import_module(package_name)
                if not hasattr(package, "__path__"):
                    continue

                # 只扫描 base 和直接实现目录
                for _, modname, _ in pkgutil.walk_packages(
                    path=package.__path__, prefix=package_name + ".", onerror=lambda x: None
                ):
                    # 只导入 base 模块和一级实现模块（避免深度递归）
                    parts = modname.split(".")
                    impl_dirs = ["rdbms", "cache", "vector", "embedder", "llm", "classifier", "clusterer"]
                    if len(parts) <= 3 and ("base" in parts or any(impl in parts for impl in impl_dirs)):
                        if modname not in scanned_modules:
                            try:
                                importlib.import_module(modname)
                                scanned_modules.add(modname)
                                logger.debug(f"Auto-imported {modname}")
                            except Exception as e:
                                logger.debug(f"Skip importing {modname}: {e}")
            except (ImportError, AttributeError) as e:
                logger.debug(f"Package {package_name} not found: {e}")

    def _generate_main_config(self) -> type[BaseSettings]:
        """自动生成主配置类

        扫描所有已注册的配置（包括 @register_config 和 @register_provider）
        并动态生成一个包含所有配置的主配置类。

        Returns:
            动态生成的主配置类
        """
        from pydantic import Field

        # 尝试导入 ProviderRegistry
        try:
            from .register import ProviderRegistry

            has_provider_registry = True
        except ImportError:
            has_provider_registry = False

        # 收集所有配置字段
        fields: Dict[str, Any] = {}
        annotations: Dict[str, Any] = {}

        # 1. 添加基础应用配置
        annotations["app_name"] = str
        fields["app_name"] = Field("distill", description="应用名称")

        annotations["debug"] = bool
        fields["debug"] = Field(False, description="调试模式")

        annotations["log_level"] = str
        fields["log_level"] = Field("INFO", description="日志级别")

        # 2. 从 ConfigRegistry 收集已注册的配置
        for config_name, metadata in self._registry.list_configs().items():
            if metadata.get("is_main"):
                continue  # 跳过主配置标记
            # 使用 Dict 而不是嵌套配置类，避免 pydantic-settings 冲突
            annotations[config_name] = Dict[str, Any]
            fields[config_name] = Field(default_factory=dict, description=metadata.get("description", ""))

        # 3. 从 ProviderRegistry 收集自动生成的配置类
        if has_provider_registry:
            # 获取所有 provider 组的配置名称
            provider_groups = ProviderRegistry.get_all_provider_groups()

            # 按配置名称分组 provider
            configs_by_group: Dict[str, Dict[str, type]] = {}

            for provider_name in ProviderRegistry.available_providers():
                config_cls = ProviderRegistry.get_config_class(provider_name)
                base_class_name = ProviderRegistry.get_base_class_for_provider(provider_name)

                if config_cls and base_class_name:
                    # 从 provider 组获取配置名称
                    config_name = provider_groups.get(base_class_name)

                    if config_name:
                        if config_name not in configs_by_group:
                            configs_by_group[config_name] = {}

                        configs_by_group[config_name][provider_name] = config_cls

            # 为每个配置组创建字段（包含 provider 字段和具体 provider 配置）
            for config_name in configs_by_group:
                if config_name not in annotations:  # 避免覆盖已注册的配置
                    # 添加 {config_name} 字段（包含 provider 和所有 provider 的配置）
                    annotations[config_name] = Dict[str, Any]
                    fields[config_name] = Field(default_factory=dict, description=f"{config_name} 配置")

        # 4. 动态创建主配置类
        namespace = {
            "__annotations__": annotations,
            "model_config": SettingsConfigDict(
                env_prefix="APP_",
                case_sensitive=False,
                env_nested_delimiter="__",
                extra="ignore",
            ),
            **fields,
        }

        # 创建动态类
        DynamicMainConfig = type("AutoGeneratedAppSettings", (BaseSettings,), namespace)

        return DynamicMainConfig

    def _build_config_dict(
        self,
        recursive_env: bool,
        start_path: Optional[Path],
    ) -> Dict[str, Any]:
        """构建 pydantic-settings 配置字典

        Args:
            recursive_env: 是否递归查找 .env
            start_path: 递归查找起始路径

        Returns:
            配置字典
        """
        config_dict: Dict[str, Any] = {
            "case_sensitive": False,
            "env_nested_delimiter": "__",
        }

        # 处理配置文件路径
        # 注意：YAML/TOML/JSON 文件通过 _load_file_data() 处理，不放在 model_config 中
        # 因为 pydantic-settings 需要额外配置 YamlConfigSettingsSource 等才能使用
        if self.env_file:
            # 指定了具体的 env_file，使用它
            config_dict["env_file"] = str(self.env_file)
            config_dict["env_file_encoding"] = "utf-8"
        elif recursive_env:
            # 递归查找 .env 文件
            env_files = find_env_files_recursive(start_path)
            if env_files:
                # pydantic-settings 支持多个 .env 文件
                # 列表中后面的文件优先级更高
                config_dict["env_file"] = [str(f) for f in env_files]
                config_dict["env_file_encoding"] = "utf-8"

        return config_dict

    def _load_file_data(self) -> Optional[Dict[str, Any]]:
        """从配置文件加载数据

        Returns:
            配置数据字典，如果没有配置文件返回 None
        """
        from .config_file_parser import parse_config_file

        if self.toml_file:
            return parse_config_file(self.toml_file)
        if self.yaml_file:
            return parse_config_file(self.yaml_file)
        if self.json_file:
            return parse_config_file(self.json_file)
        return None

    def list_registered_configs(self) -> Dict[str, Dict[str, Any]]:
        """列出所有已注册的配置

        Returns:
            配置元数据字典
        """
        return self._registry.list_configs()

    def get_main_config_info(self) -> Optional[Dict[str, Any]]:
        """获取主配置信息

        Returns:
            主配置元数据，如果没有主配置返回 None
        """
        main_name = self._registry.get_main_config_name()
        if main_name:
            configs = self._registry.list_configs()
            return configs.get(main_name)
        return None


# 便捷函数
def load_config(
    env_file: Optional[str | Path] = None,
    toml_file: Optional[str | Path] = None,
    yaml_file: Optional[str | Path] = None,
    json_file: Optional[str | Path] = None,
    recursive_env: bool = True,
    start_path: Optional[Path] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
    auto_generate: bool = True,
    provider_modules: Optional[list[str]] = None,
) -> BaseSettings:
    """便捷函数：快速加载主配置

    Args:
        env_file: .env 文件路径
        toml_file: TOML 配置文件路径
        yaml_file: YAML 配置文件路径
        json_file: JSON 配置文件路径
        recursive_env: 是否递归查找 .env 文件
        start_path: 递归查找的起始路径
        config_overrides: 配置覆盖值
        auto_generate: 如果没有主配置，是否自动生成（默认 True）
        provider_modules: 需要导入的 provider 模块列表，None 则自动扫描

    Returns:
        已实例化的主配置对象

    Examples:
        >>> from distill_utils.config import load_config
        >>>
        >>> # 使用自动生成的主配置（默认）
        >>> settings = load_config()
        >>>
        >>> # 使用指定的 .env 文件
        >>> settings = load_config(env_file="/app/.env.prod", recursive_env=False)
        >>>
        >>> # 使用 TOML 配置（自动扫描并包含所有 provider 配置）
        >>> settings = load_config(toml_file="/app/config.toml")
        >>>
        >>> # 指定要导入的 provider 模块（加快加载速度）
        >>> settings = load_config(
        ...     yaml_file="/app/config.yaml",
        ...     provider_modules=["distill_dao.base.rdbms", "distill_dao.rdbms.duckdb_dao_impl"],
        ... )
    """
    loader = ConfigLoader(
        env_file=env_file,
        toml_file=toml_file,
        yaml_file=yaml_file,
        json_file=json_file,
        provider_modules=provider_modules,
    )
    return loader.load(
        recursive_env=recursive_env,
        start_path=start_path,
        config_overrides=config_overrides,
        auto_generate=auto_generate,
    )


def load_config_file(
    config_file: str,
    env_file: Optional[str | Path] = None,
    provider_modules: Optional[list[str]] = None,
) -> BaseSettings:
    """便捷函数：根据配置文件路径加载主配置

    Args:
        config_file: 配置文件路径（支持 .toml, .yaml, .json）
        env_file: .env 文件路径
        provider_modules: 需要导入的 provider 模块列表，None 则自动扫描
    Returns:
        已实例化的主配置对象
    """
    toml_file = None
    yaml_file = None
    json_file = None
    config_path = Path(config_file)
    if config_path.suffix in [".toml", ".tml"]:
        toml_file = config_file
    elif config_path.suffix in [".yaml", ".yml"]:
        yaml_file = config_file
    elif config_path.suffix == ".json":
        json_file = config_file
    else:
        raise ValueError("不支持的配置文件格式，仅支持 .toml, .yaml, .json")

    return load_config(
        env_file=env_file,
        toml_file=toml_file,
        yaml_file=yaml_file,
        json_file=json_file,
        recursive_env=True,
        provider_modules=provider_modules,
    )


__all__ = [
    "ConfigLoader",
    "load_config",
    "load_config_file",
]
