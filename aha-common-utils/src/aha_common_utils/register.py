import inspect
import multiprocessing
import multiprocessing.managers
import multiprocessing.synchronize
from abc import ABCMeta
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar, Union, cast

from .logging import get_logger

T = TypeVar("T")

logger = get_logger(__name__)


class ProviderRegistry:
    """全局 Provider 注册表

    使用装饰器模式注册实现类，支持多进程环境和单例模式。
    """

    # 本地注册表: provider_name -> class_type
    _registry: Dict[str, Type] = {}

    # 注册信息: provider_name -> (module_path, class_name)
    # 用于在子进程中动态导入
    _registry_info: Dict[str, Tuple[str, str]] = {}

    # 单例实例缓存: provider_name -> instance
    _instances: Dict[str, Any] = {}
    _instance_lock = multiprocessing.Lock()

    # 标记哪些 provider 是单例: provider_name -> bool
    _singleton_flags: Dict[str, bool] = {}

    # 配置路径: provider_name -> config_path (如 "cache.diskcache")
    _config_paths: Dict[str, str] = {}

    # 配置类缓存: provider_name -> BaseSettings class
    _config_classes: Dict[str, Type] = {}

    # 参数信息缓存: provider_name -> params_info
    _params_info: Dict[str, Dict[str, Dict[str, Any]]] = {}

    # 基类映射: provider_name -> base_class_name
    # 在注册时自动提取，用于依赖注入
    _base_class_mapping: Dict[str, str] = {}

    # Provider 组注册: base_class_name -> config_name
    # 用于管理 provider 组的配置名称
    _provider_groups: Dict[str, str] = {}

    # 全局配置文件路径
    _global_config_file: Optional[str] = None

    # 全局配置数据缓存（从配置文件加载的完整配置）
    _global_config_data: Optional[Dict[str, Any]] = None

    # 多进程共享管理器
    _manager: Optional[multiprocessing.managers.SyncManager] = None
    _shared_registry: Optional[Union[Dict[str, tuple], multiprocessing.managers.DictProxy]] = None
    _lock: Optional[Any] = None
    _multiprocessing_enabled: bool = False

    @classmethod
    def _extract_base_class_name(cls, impl_cls: Type) -> Optional[str]:
        """从实现类中提取基类名称

        通过检查 MRO 找到第一个非标准库的基类（业务基类）。
        完全业务无关，不依赖任何特定的包名前缀。

        Args:
            impl_cls: 实现类

        Returns:
            基类名称（如 'CacheDao', 'BaseLLM'），如果无法提取则返回 None
        """
        if not inspect.isclass(impl_cls):
            return None

        # Python 标准库模块前缀列表（更完整）
        stdlib_prefixes = (
            "builtins",
            "abc",
            "typing",
            "collections",
            "functools",
            "itertools",
            "operator",
            "pathlib",
            "os",
            "sys",
            "io",
            "re",
            "json",
            "pickle",
            "copy",
            "weakref",
            "gc",
            "inspect",
            "dis",
            "importlib",
            "pkgutil",
            "modulefinder",
            "_",
            "__future__",
            "__main__",
        )

        # 遍历 MRO（跳过自身）
        for base in impl_cls.__mro__[1:]:
            base_name = base.__name__
            base_module = getattr(base, "__module__", "")

            # 跳过内置基类
            if base_name in ("object", "ABC", "ABCMeta", "Generic", "type"):
                continue

            # 跳过标准库模块
            if any(base_module == prefix or base_module.startswith(prefix + ".") for prefix in stdlib_prefixes):
                continue

            # 找到第一个非标准库的基类（即业务基类）
            return base_name

        return None

    @classmethod
    def get_base_class_for_provider(cls, provider_name: str) -> Optional[str]:
        """获取 provider 对应的基类名称

        Args:
            provider_name: provider 名称

        Returns:
            基类名称，如果未找到则返回 None
        """
        return cls._base_class_mapping.get(provider_name)

    @classmethod
    def get_providers_for_base_class(cls, base_class_name: str) -> List[str]:
        """获取某个基类的所有 provider 名称（智能类型推断）

        从已注册 provider 的 MRO 中动态发现目标基类对象，
        再使用 issubclass 检查继承关系，无需硬编码导入映射表。

        Args:
            base_class_name: 基类名称字符串（如 "BaseLLM", "BaseEmbedder", "CacheDao" 等）

        Returns:
            匹配的 provider 名称列表

        Examples:
            >>> ProviderRegistry.get_providers_for_base_class("BaseLLM")
            ['openai-llm']
            >>> ProviderRegistry.get_providers_for_base_class("CacheDao")
            ['diskcache']
        """
        all_providers = list(cls._registry.keys())

        # 从已注册 provider 的 MRO 中动态发现目标基类对象，避免硬编码 import
        base_class = None
        for provider_name in all_providers:
            provider_class = cls._registry.get(provider_name)
            if provider_class is None or not inspect.isclass(provider_class):
                continue
            for klass in provider_class.__mro__:
                if klass.__name__ == base_class_name:
                    base_class = klass
                    break
            if base_class is not None:
                break

        if base_class is None:
            logger.debug(f"[get_providers_for_base_class] Unknown base class: {base_class_name}")
            return []

        # 使用 issubclass 检查继承关系，准确匹配所有子类实现
        matching = []
        for provider_name in all_providers:
            try:
                provider_class = cls._registry.get(provider_name)
                if provider_class is None:
                    continue
                if inspect.isclass(provider_class) and issubclass(provider_class, base_class):
                    matching.append(provider_name)
                    logger.debug(f"[get_providers_for_base_class] Matched {provider_name} for {base_class_name}")
            except (TypeError, AttributeError) as e:
                logger.debug(f"[get_providers_for_base_class] Skip {provider_name}: {e}")
                continue

        return matching

    @classmethod
    def register_provider_group(cls, base_class_name: str, config_name: str):
        """注册 provider 组的配置名称

        Args:
            base_class_name: 基类名称（如 'RDBMS', 'CacheDao'）
            config_name: 配置名称（如 'rdbms', 'cache'）
        """
        cls._provider_groups[base_class_name] = config_name
        logger.debug(f"[ProviderRegistry] Registered provider group: {base_class_name} -> {config_name}")

    @classmethod
    def get_config_name_for_group(cls, base_class_name: str) -> Optional[str]:
        """获取 provider 组的配置名称

        Args:
            base_class_name: 基类名称

        Returns:
            配置名称，如果未注册则返回 None
        """
        return cls._provider_groups.get(base_class_name)

    @classmethod
    def get_all_provider_groups(cls) -> Dict[str, str]:
        """获取所有已注册的 provider 组

        Returns:
            基类名称到配置名称的映射字典
        """
        return cls._provider_groups.copy()

    @classmethod
    def register(
        cls,
        name: str,
        singleton: bool = True,
        config_path: Optional[str] = None,
    ) -> Callable[[Type[T]], Type[T]]:
        """装饰器：注册实现类

        用法:
            @ProviderRegistry.register("ASR-Whisper")
            class ASRLocalTransformersImpl(ASR):
                ...

            # 非单例模式
            @ProviderRegistry.register("ASR-Whisper", singleton=False)
            class ASRLocalTransformersImpl(ASR):
                ...

            # 带配置路径（用于生成配置类）
            @ProviderRegistry.register("diskcache", config_path="cache.diskcache")
            class DiskCacheDaoImpl(CacheDao):
                def __init__(
                    self,
                    directory: Annotated[str, ParamMeta(description="缓存目录")] = ".cache",
                    size_limit: Annotated[int, ParamMeta(description="缓存大小", ge=0)] = 1024*1024*1024,
                ):
                    ...

        Args:
            name: provider 名称
            singleton: 是否使用单例模式，默认 True
            config_path: 配置路径（如 "cache.diskcache"），用于生成 BaseSettings 配置类

        Returns:
            装饰器函数
        """

        def decorator(impl_cls: Type[T]) -> Type[T]:
            # 注册到本地注册表
            cls._registry[name] = impl_cls
            cls._singleton_flags[name] = singleton

            # 保存模块信息用于动态导入
            module_path = impl_cls.__module__
            class_name = impl_cls.__qualname__
            cls._registry_info[name] = (module_path, class_name)

            # 自动提取基类信息（用于依赖注入）
            try:
                base_class_name = cls._extract_base_class_name(impl_cls)
                if base_class_name:
                    cls._base_class_mapping[name] = base_class_name
                    logger.debug(f"[ProviderRegistry] Mapped {name} -> {base_class_name}")
            except Exception as e:
                logger.warning(f"[ProviderRegistry] Failed to extract base class for {name}: {e}")

            # 扫描所有参数（用于依赖注入），无论是否有 config_path
            try:
                from .config_generator import ParamScanner

                all_params_info = ParamScanner.scan_all_params(impl_cls)
                cls._params_info[name] = all_params_info
            except Exception as e:
                logger.warning(f"[ProviderRegistry] Failed to scan params for {name}: {e}")

            # 保存配置路径
            if config_path:
                cls._config_paths[name] = config_path

                # 扫描参数并生成配置类
                try:
                    from .config_generator import ConfigClassGenerator, ParamScanner

                    # 只扫描配置参数（有 ParamMeta 的）用于生成配置类
                    config_params_info = ParamScanner.scan_init_params(impl_cls)

                    if config_params_info:
                        config_cls = ConfigClassGenerator.generate_config_class(name, config_path, config_params_info)
                        cls._config_classes[name] = config_cls
                        logger.debug(
                            f"[ProviderRegistry] Generated config class {config_cls.__name__} "
                            f"for {name} at path {config_path}"
                        )
                except Exception as e:
                    logger.warning(f"[ProviderRegistry] Failed to generate config for {name}: {e}")

            logger.debug(f"[ProviderRegistry] Registered {name} -> {module_path}.{class_name} (singleton={singleton})")

            # 如果已启用多进程模式，同步到共享注册表
            if cls._multiprocessing_enabled and cls._shared_registry is not None:
                cls._sync_to_shared(name, module_path, class_name, singleton)

            return impl_cls

        return decorator

    @classmethod
    def _sync_to_shared(cls, name: str, module_path: str, class_name: str, singleton: bool = True):
        """同步单个注册项到共享注册表"""
        if cls._lock is None or cls._shared_registry is None:
            return
        try:
            with cls._lock:
                cls._shared_registry[name] = (module_path, class_name, singleton)
                logger.debug(f"[ProviderRegistry] Synced {name} to shared registry")
        except Exception as e:
            logger.warning(f"[ProviderRegistry] Failed to sync {name}: {e}")

    @classmethod
    def enable_multiprocessing(cls):
        """启用多进程模式

        必须在主进程中、创建子进程之前调用。
        """
        if cls._multiprocessing_enabled:
            return

        cls._manager = multiprocessing.Manager()
        cls._shared_registry = cls._manager.dict()
        cls._lock = cls._manager.Lock()
        cls._multiprocessing_enabled = True

        # 同步所有已注册的类到共享注册表
        with cls._lock:
            for name, (module_path, class_name) in cls._registry_info.items():
                singleton = cls._singleton_flags.get(name, True)
                cls._shared_registry[name] = (module_path, class_name, singleton)

        logger.info(f"[ProviderRegistry] Multiprocessing enabled, synced {len(cls._registry_info)} providers")

    @classmethod
    def is_multiprocessing_enabled(cls) -> bool:
        """检查是否已启用多进程模式"""
        return cls._multiprocessing_enabled

    @classmethod
    def get(cls, name: str) -> Optional[Type]:
        """获取已注册的类

        Args:
            name: provider 名称

        Returns:
            注册的类，如果未找到则返回 None
        """
        # 1. 优先从本地注册表查找
        if name in cls._registry:
            return cls._registry[name]

        # 2. 如果启用了多进程模式，从共享注册表查找并动态导入
        if cls._multiprocessing_enabled and cls._shared_registry is not None:
            try:
                class_info = cls._shared_registry.get(name)
                if class_info:
                    # 支持新格式 (module, class, singleton) 和旧格式 (module, class)
                    if len(class_info) == 3:
                        module_path, class_name, singleton = class_info
                        cls._singleton_flags[name] = singleton
                    else:
                        module_path, class_name = class_info
                        cls._singleton_flags[name] = True  # 默认单例

                    impl_cls = cls._import_class(module_path, class_name)
                    if impl_cls:
                        # 缓存到本地注册表
                        cls._registry[name] = impl_cls
                        cls._registry_info[name] = (module_path, class_name)
                        logger.debug(f"[ProviderRegistry] Loaded {name} from shared registry")
                        return impl_cls
            except Exception as e:
                logger.warning(f"[ProviderRegistry] Failed to load {name} from shared: {e}")

        return None

    @classmethod
    def is_singleton(cls, name: str) -> bool:
        """检查 provider 是否为单例模式"""
        return cls._singleton_flags.get(name, True)

    @classmethod
    def get_instance(cls, name: str, *args, **kwargs) -> Any:
        """获取 provider 实例（支持单例模式）

        Args:
            name: provider 名称
            *args: 构造函数位置参数
            **kwargs: 构造函数关键字参数

        Returns:
            provider 实例

        Raises:
            ValueError: provider 未找到
        """
        impl_cls = cls.get(name)
        if not impl_cls:
            raise ValueError(f"Provider not found: {name}")

        # 如果是单例模式，从缓存获取或创建
        if cls.is_singleton(name):
            if name not in cls._instances:
                with cls._instance_lock:
                    if name not in cls._instances:
                        cls._instances[name] = impl_cls(*args, **kwargs)
                        logger.debug(f"[ProviderRegistry] Created singleton instance for {name}")
            return cls._instances[name]

        # 非单例模式，每次创建新实例
        return impl_cls(*args, **kwargs)

    @classmethod
    def clear_instance(cls, name: str):
        """清除指定 provider 的单例实例缓存"""
        with cls._instance_lock:
            if name in cls._instances:
                del cls._instances[name]
                logger.debug(f"[ProviderRegistry] Cleared singleton instance for {name}")

    @classmethod
    def clear_all_instances(cls):
        """清除所有单例实例缓存"""
        with cls._instance_lock:
            cls._instances.clear()
            logger.debug("[ProviderRegistry] Cleared all singleton instances")

    @classmethod
    def _import_class(cls, module_path: str, class_name: str) -> Optional[Type]:
        """动态导入类"""
        try:
            module = __import__(module_path, fromlist=[class_name.split(".")[0]])
            # 处理嵌套类名 (如 Outer.Inner)
            obj = module
            for part in class_name.split("."):
                obj = getattr(obj, part)
            return cast(Type, obj)
        except Exception as e:
            logger.error(f"[ProviderRegistry] Import failed: {module_path}.{class_name}: {e}")
            return None

    @classmethod
    def get_all(cls) -> Dict[str, Type]:
        """获取所有已注册的类"""
        result = dict(cls._registry)

        # 如果启用了多进程模式，也加载共享注册表中的类
        if cls._multiprocessing_enabled and cls._shared_registry is not None:
            try:
                for name in cls._shared_registry.keys():
                    if name not in result:
                        impl = cls.get(name)
                        if impl:
                            result[name] = impl
            except Exception as e:
                logger.warning(f"[ProviderRegistry] Failed to get all from shared: {e}")

        return result

    @classmethod
    def available_providers(cls) -> List[str]:
        """获取所有可用的 provider 名称"""
        names = set(cls._registry.keys())
        if cls._multiprocessing_enabled and cls._shared_registry is not None:
            try:
                names.update(cls._shared_registry.keys())
            except Exception:
                pass
        return sorted(names)

    @classmethod
    def set_config_file(cls, config_file: str):
        """设置全局配置文件路径

        设置后，所有 get_instance_from_config 调用都会自动使用此配置文件，
        除非显式传入 config_file 参数覆盖。

        Args:
            config_file: 配置文件路径（支持 .yaml/.yml/.toml/.json）

        Examples:
            >>> # 启动时设置一次
            >>> ProviderRegistry.set_config_file("config.yaml")
            >>>
            >>> # 后续所有调用都自动使用此配置
            >>> cache = ProviderRegistry.get_instance_from_config(CacheDao, "diskcache")
            >>> embedder = ProviderRegistry.get_instance_from_config(Embedder, "openai-embedder")
        """
        from .config_file_parser import parse_config_file

        cls._global_config_file = config_file
        try:
            # 预加载并缓存配置数据
            cls._global_config_data = parse_config_file(config_file)
            logger.info(f"Loaded global config from {config_file}")
        except Exception as e:
            logger.error(f"Failed to load global config from {config_file}: {e}")
            cls._global_config_data = None

    @classmethod
    def get_config_file(cls) -> Optional[str]:
        """获取当前设置的全局配置文件路径"""
        return cls._global_config_file

    @classmethod
    def clear_config_file(cls):
        """清除全局配置文件设置"""
        cls._global_config_file = None
        cls._global_config_data = None
        logger.debug("Cleared global config file")

    @classmethod
    def get_config_class(cls, name: str) -> Optional[Type]:
        """获取 provider 的配置类

        Args:
            name: provider 名称

        Returns:
            BaseSettings 配置类，如果未找到则返回 None
        """
        return cls._config_classes.get(name)

    @classmethod
    def get_config_path(cls, name: str) -> Optional[str]:
        """获取 provider 的配置路径

        Args:
            name: provider 名称

        Returns:
            配置路径（如 "cache.diskcache"），如果未找到则返回 None
        """
        return cls._config_paths.get(name)

    @classmethod
    def get_params_info(cls, name: str) -> Dict[str, Dict[str, Any]]:
        """获取 provider 的参数信息

        Args:
            name: provider 名称

        Returns:
            参数信息字典
        """
        return cls._params_info.get(name, {})

    @classmethod
    def find_provider_by_class(cls, type_cls: Type) -> Optional[str]:
        """根据类查找对应的 provider 名称

        Args:
            type_cls: 要查找的类

        Returns:
            provider 名称，如果未找到则返回 None
        """
        for name, registered_cls in cls._registry.items():
            if registered_cls is type_cls:
                return name
        return None

    @classmethod
    def get_instance_from_config(
        cls,
        type_cls: Type[T],
        provider_name: str,
        config_file: Optional[str] = None,
        config_override: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> T:
        """从配置自动实例化类

        该方法会：
        1. 根据 provider 名称查找实现类
        2. 从配置文件或环境变量加载配置（如果存在）
        3. 合并配置文件、环境变量和 kwargs（优先级递增）
        4. 使用完整参数实例化类

        配置优先级（从低到高）：
        1. 默认值
        2. 环境变量
        3. 配置文件（config_file）
        4. config_override
        5. kwargs

        Args:
            type_cls: 基类类型（如 CacheDao, Embedder）
            provider_name: provider 名称（如 "diskcache", "openai-embedder"）
            config_file: 配置文件路径（支持 .yaml/.yml/.toml/.json），可选
            config_override: 配置覆盖字典
            **kwargs: 额外参数（优先级最高）

        Returns:
            实例化的对象

        Raises:
            ValueError: provider 未注册、类型不匹配或实例化失败

        Examples:
            >>> # 1. 基于基类和 provider 名称实例化（从环境变量加载）
            >>> cache = ProviderRegistry.get_instance_from_config(CacheDao, "diskcache")
            >>>
            >>> # 2. 从配置文件加载
            >>> cache = ProviderRegistry.get_instance_from_config(
            ...     CacheDao, "diskcache", config_file="/path/to/config.yaml"
            ... )
            >>>
            >>> # 3. 覆盖特定参数
            >>> cache = ProviderRegistry.get_instance_from_config(
            ...     CacheDao, "diskcache", config_file="config.yaml", config_override={"directory": "/custom/cache"}
            ... )
            >>>
            >>> # 4. 使用 kwargs 覆盖（优先级最高）
            >>> embedder = ProviderRegistry.get_instance_from_config(
            ...     Embedder, "openai-embedder", config_file="config.yaml", api_key="sk-xxx"
            ... )
        """
        # 1. 根据 provider 名称获取实现类
        impl_cls = cls.get(provider_name)
        if not impl_cls:
            available = cls.available_providers()
            raise ValueError(f"Provider '{provider_name}' not found. Available providers: {', '.join(available)}")

        # 2. 验证实现类是否为基类的子类
        if not issubclass(impl_cls, type_cls):
            raise ValueError(
                f"Provider '{provider_name}' ({impl_cls.__name__}) is not a subclass of {type_cls.__name__}"
            )

        # 3. 如果是单例且已存在，检查是否需要使用缓存实例
        if cls.is_singleton(provider_name) and provider_name in cls._instances:
            # 如果没有提供任何覆盖参数，直接返回缓存实例
            # 注意：config_file 不算覆盖参数，因为可能加载相同的配置
            if not config_override and not kwargs:
                logger.debug(f"Returning cached singleton instance for {provider_name}")
                return cls._instances[provider_name]
            else:
                # 只有 config_override 或 kwargs 时才清除旧实例
                logger.debug(f"Clearing cached instance for {provider_name} due to parameter override")
                cls.clear_instance(provider_name)

        # 4. 加载配置
        params = {}
        config_cls = cls.get_config_class(provider_name)

        if config_cls:
            try:
                # 实例化配置类（会自动从环境变量加载）
                config = config_cls()
                # 将配置转换为字典
                params = config.model_dump()
                logger.debug(f"Loaded config from env for {provider_name}: {list(params.keys())}")
            except Exception as e:
                logger.warning(f"Failed to load config from env for {provider_name}: {e}")

        # 5. 从配置文件加载（会覆盖环境变量）
        # 优先使用传入的 config_file，其次使用全局配置
        actual_config_file = config_file or cls._global_config_file

        if actual_config_file:
            try:
                file_config = cls._load_config_from_file(actual_config_file, provider_name)
                if file_config:
                    params.update(file_config)
                    source = "file" if config_file else "global config"
                    logger.debug(f"Loaded config from {source} for {provider_name}: {list(file_config.keys())}")
            except Exception as e:
                logger.warning(f"Failed to load config from file {actual_config_file}: {e}")

        # 6. 应用配置覆盖
        if config_override:
            params.update(config_override)
            logger.debug(f"Applied config override for {provider_name}: {list(config_override.keys())}")

        # 7. 应用 kwargs 覆盖（优先级最高）
        if kwargs:
            params.update(kwargs)
            logger.debug(f"Applied kwargs override for {provider_name}: {list(kwargs.keys())}")

        # 8. 使用 get_instance 创建实例（支持单例）
        try:
            instance = cls.get_instance(provider_name, **params)
            logger.info(f"Successfully created instance of {provider_name} ({type_cls.__name__}) from config")
            return cast(T, instance)
        except Exception as e:
            logger.error(f"Failed to instantiate {provider_name}: {e}")
            raise ValueError(f"Failed to instantiate {provider_name} ({type_cls.__name__}): {e}") from e

    @classmethod
    def _load_config_from_file(cls, config_file: str, provider_name: str) -> Dict[str, Any]:
        """从配置文件加载指定 provider 的配置

        根据 config_path（如 "cache.diskcache"）从配置文件中提取对应的配置段。
        复用 config_file_parser 模块的功能。
        如果配置文件是全局配置文件且已缓存，则使用缓存数据。

        Args:
            config_file: 配置文件路径（支持 .yaml/.yml/.toml/.json）
            provider_name: provider 名称

        Returns:
            配置字典

        Raises:
            ValueError: 不支持的文件格式或文件不存在
            Exception: 文件解析错误
        """
        from .config_file_parser import extract_nested_config, parse_config_file

        # 获取 provider 的配置路径
        config_path = cls.get_config_path(provider_name)
        if not config_path:
            logger.warning(f"No config_path found for {provider_name}, returning empty config")
            return {}

        # 如果是全局配置文件且已缓存，直接使用缓存
        if config_file == cls._global_config_file and cls._global_config_data is not None:
            return extract_nested_config(cls._global_config_data, config_path)

        # 否则解析配置文件
        try:
            config_data = parse_config_file(config_file)
            return extract_nested_config(config_data, config_path)
        except Exception as e:
            logger.warning(f"Failed to load config from {config_file} for {provider_name}: {e}")
            return {}


# 便捷别名
register_provider = ProviderRegistry.register


def register_provider_group(config_name: str) -> Callable[[Type[T]], Type[T]]:
    """装饰器：注册 provider 组的配置名称

    用于装饰抽象基类，声明该 provider 组在配置文件中的名称。

    Args:
        config_name: 配置名称（如 'rdbms', 'cache'）

    Returns:
        装饰器函数

    Examples:
        >>> from abc import ABC, abstractmethod
        >>> from distill_utils.register import register_provider_group
        >>>
        >>> @register_provider_group("rdbms")
        >>> class RDBMS(ABC):
        ...     @abstractmethod
        ...     def connect(self): ...
        >>>
        >>> # 配置文件中使用:
        >>> # rdbms_provider: duckdb
        >>> # rdbms:
        >>> #   duckdb:
        >>> #     db_url: "..."
    """

    def decorator(base_class: Type[T]) -> Type[T]:
        base_class_name = base_class.__name__
        ProviderRegistry.register_provider_group(base_class_name, config_name)
        return base_class

    return decorator


class RegistryManager:
    """进程安全的注册表管理器

    使用 multiprocessing.Manager 实现跨进程的注册表共享。
    注册表存储 provider_name -> (module_path, class_name) 映射。
    """

    _manager: Optional[multiprocessing.managers.SyncManager] = None
    _shared_registry: Optional[Union[Dict[str, tuple], multiprocessing.managers.DictProxy]] = None
    _lock: Optional[Any] = None  # Lock or proxy to Lock
    _initialized: bool = False

    @classmethod
    def init(cls):
        """初始化共享注册表（仅在主进程调用一次）"""
        if not cls._initialized:
            cls._manager = multiprocessing.Manager()
            cls._shared_registry = cls._manager.dict()
            cls._lock = cls._manager.Lock()
            cls._initialized = True
            logger.debug("RegistryManager initialized for multiprocessing")

    @classmethod
    def is_enabled(cls) -> bool:
        """检查是否已启用多进程模式"""
        return cls._initialized and cls._shared_registry is not None

    @classmethod
    def register(cls, name: str, class_type: Type):
        """注册类到共享注册表

        Args:
            name: provider 名称
            class_type: 要注册的类
        """
        if not cls.is_enabled():
            return  # 未启用多进程模式，跳过

        if cls._lock is None:
            logger.warning(f"Lock not initialized, cannot register {name}")
            return

        try:
            with cls._lock:
                if cls._shared_registry is None:
                    logger.warning(f"Shared registry not initialized, cannot register {name}")
                    return
                module = class_type.__module__
                qualname = class_type.__qualname__
                cls._shared_registry[name] = (module, qualname)
                logger.debug(f"Registered {name} -> {module}.{qualname} to shared registry")
        except Exception as e:
            logger.warning(f"Failed to register {name} to shared registry: {e}")

    @classmethod
    def get(cls, name: str) -> Optional[Type]:
        """从共享注册表获取类

        Args:
            name: provider 名称

        Returns:
            注册的类，如果未找到则返回 None
        """
        if not cls.is_enabled():
            return None

        if cls._shared_registry is None:
            return None

        try:
            class_info = cls._shared_registry.get(name)
            if not class_info:
                return None

            module_name, class_name = class_info
            # 动态导入模块和类
            module = __import__(module_name, fromlist=[class_name])
            class_type = getattr(module, class_name)
            logger.debug(f"Loaded {name} -> {module_name}.{class_name} from shared registry")
            return class_type
        except Exception as e:
            logger.warning(f"Failed to load {name} from shared registry: {e}")
            return None

    @classmethod
    def get_all_providers(cls) -> Dict[str, tuple]:
        """获取所有已注册的 provider"""
        if not cls.is_enabled():
            return {}
        if cls._shared_registry is None:
            return {}
        return dict(cls._shared_registry)


class SingletonMeta(type):
    """单例元类

    确保每个类在进程内只有一个实例。
    注意：多进程环境下，每个进程有独立的单例实例。
    """

    _instances: Dict[Type, Any] = {}
    _lock = multiprocessing.Lock()

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]


class RegsiterMeta(type):
    """注册元类

    自动注册带有 'name' 属性的子类到注册表。
    支持本地注册表和可选的跨进程共享注册表。
    """

    _registry: Dict[str, Type] = {}
    _use_multiprocessing: bool = False

    def __init__(cls, name, bases, dct):
        super().__init__(name, bases, dct)
        if not hasattr(cls, "_registry"):
            cls._registry = {}  # 基类初始化注册表
        elif "name" in dct and dct["name"]:
            # 注册到本地注册表
            cls._registry[dct["name"]] = cls
            logger.debug(f"Registered {dct['name']} -> {cls.__name__} to local registry")

            # 如果启用多进程模式，也注册到共享注册表
            if cls._use_multiprocessing:
                RegistryManager.register(dct["name"], cls)

    @classmethod
    def registry(cls) -> Dict[str, Type]:
        """获取本地注册表"""
        return cls._registry

    @classmethod
    def enable_multiprocessing(cls):
        """启用多进程模式

        必须在主进程中、创建子进程之前调用。
        启用后，所有注册的类都会同步到跨进程共享注册表。
        """
        if not cls._use_multiprocessing:
            cls._use_multiprocessing = True
            RegistryManager.init()

            # 将已注册的类同步到共享注册表
            for provider_name, class_type in cls._registry.items():
                RegistryManager.register(provider_name, class_type)

            logger.info(f"Multiprocessing mode enabled, synced {len(cls._registry)} providers")

    @classmethod
    def is_multiprocessing_enabled(cls) -> bool:
        """检查是否启用了多进程模式"""
        return cls._use_multiprocessing and RegistryManager.is_enabled()


class SingletonRegisterMeta(SingletonMeta, RegsiterMeta, ABCMeta):
    """单例 + 注册 + 抽象基类的组合元类

    同时提供：
    1. 单例模式（每个进程内唯一实例）
    2. 自动注册机制
    3. 抽象基类支持
    4. 可选的跨进程注册表共享
    """

    pass


class RegisterABCMeta(RegsiterMeta, ABCMeta):
    """注册 + 抽象基类的组合元类"""

    pass


class ClassFactory:
    """类工厂：根据 provider 名称创建实例

    支持新的装饰器注册表（ProviderRegistry）和旧的元类注册表（RegsiterMeta）。
    优先使用 ProviderRegistry（支持单例），回退到旧的注册机制。
    """

    @staticmethod
    def get_instance(provider_name: str, type_cls: Type[T], *args, **kwargs) -> T:
        """根据 provider 名称创建实例

        Args:
            provider_name: provider 名称
            type_cls: 期望的基类类型
            *args: 构造函数位置参数
            **kwargs: 构造函数关键字参数

        Returns:
            创建的实例

        Raises:
            ValueError: provider 未找到或类型不匹配
            TypeError: 尝试实例化抽象类
        """
        impl: Optional[Type[T]] = None
        use_provider_registry = False

        # 1. 优先从新的 ProviderRegistry 查找（装饰器注册，支持单例）
        impl = ProviderRegistry.get(provider_name)
        if impl:
            use_provider_registry = True

        # 2. 如果未找到，从旧的元类注册表查找
        if not impl:
            impl = SingletonRegisterMeta._registry.get(provider_name)

        # 3. 如果本地未找到且启用了多进程模式，从共享注册表查找
        if not impl and RegsiterMeta._use_multiprocessing:
            impl = RegistryManager.get(provider_name)
            if impl:
                # 缓存到本地注册表，加速后续查找
                SingletonRegisterMeta._registry[provider_name] = impl
                logger.debug(f"Cached {provider_name} to local registry from shared registry")

        # 4. 验证找到的类
        if not impl:
            # 收集所有可用的 providers
            available = list(ProviderRegistry.available_providers())
            available.extend([k for k in SingletonRegisterMeta._registry.keys() if k not in available])
            if RegsiterMeta._use_multiprocessing:
                shared_providers = RegistryManager.get_all_providers()
                available.extend([k for k in shared_providers.keys() if k not in available])
            raise ValueError(
                f"Unsupported provider: {provider_name} for {type_cls.__name__}. "
                f"Available providers: {', '.join(available) if available else 'None'}"
            )

        if not issubclass(impl, type_cls):
            raise ValueError(f"Provider {provider_name} is not a subclass of {type_cls.__name__}")

        if inspect.isabstract(impl):
            raise TypeError(f"Provider {provider_name} ({impl.__name__}) is abstract and cannot be instantiated")

        # 5. 获取构造函数签名并过滤参数
        try:
            signature = inspect.signature(impl.__init__)
        except ValueError:
            signature = inspect.signature(object.__init__)
            logger.warning(f"Using object.__init__ for {impl.__name__} as it has no __init__ method.")

        # 过滤 kwargs：只保留构造函数中声明的参数（排除 self）
        filtered_kwargs = {
            name: value for name, value in kwargs.items() if name in signature.parameters and name != "self"
        }
        logger.debug(f"Filtered kwargs for {impl.__name__}: {filtered_kwargs}")

        # 6. 如果是通过 ProviderRegistry 注册且为单例模式，使用其单例机制
        if use_provider_registry and ProviderRegistry.is_singleton(provider_name):
            instance = ProviderRegistry.get_instance(provider_name, *args, **filtered_kwargs)
            return cast(T, instance)

        # 7. 普通实例化（非单例或旧注册机制）
        instance = impl(*args, **filtered_kwargs)
        return cast(T, instance)
