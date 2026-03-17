"""智能依赖注入容器

自动解析和实例化组件依赖，减少硬编码：
- 自动识别构造函数参数类型
- 递归解析依赖关系
- 自动实例化依赖组件
- 支持配置覆盖
- 缓存单例实例

Example:
    >>> from aha_common_utils.dependency_injector import DependencyInjector
    >>> from aha_common_utils.base.cache import SemanticCache
    >>>
    >>> injector = DependencyInjector()
    >>> injector.configure("cache_provider", "diskcache", {"directory": ".cache"})
    >>> injector.configure("vector_provider", "qdrant-vector", {"embedding_size": 1024})
    >>> injector.configure("embedder_provider", "bge-m3-embedder", {})
    >>> injector.configure("semantic_cache_provider", "semantic-cache", {"collection": "llm_cache"})
    >>>
    >>> # 自动解析所有依赖并实例化
    >>> cache = injector.get(SemanticCache, "semantic-cache")
"""

import inspect
from typing import Any, Dict, List, Optional, Type, TypeVar

from .logging import get_logger
from .register import ProviderRegistry

T = TypeVar("T")

logger = get_logger(__name__)


class DependencyInjector:
    """智能依赖注入容器

    自动解析类型注解，递归创建依赖实例。
    """

    def __init__(self):
        """初始化依赖注入容器"""
        # provider 配置: base_class_name -> (provider_name, config_override)
        self._provider_config: Dict[str, tuple] = {}

        # 实例缓存: (base_class, provider_name) -> instance
        self._instance_cache: Dict[tuple, Any] = {}

        # 依赖解析栈，用于检测循环依赖
        self._resolution_stack: List[str] = []

    def configure(self, provider_key: str, provider_name: str, config_override: Optional[Dict[str, Any]] = None):
        """配置 provider

        Args:
            provider_key: provider 配置键（如 'cache_provider', 'llm_provider'）
            provider_name: provider 名称（如 'diskcache', 'openai-llm'）
            config_override: 配置覆盖

        Example:
            >>> injector.configure("cache_provider", "diskcache", {"directory": ".cache"})
            >>> injector.configure("llm_provider", "openai-llm", {"model_name": "gpt-4"})
        """
        # 动态推断基类名称（无硬编码）
        base_class_name = self._infer_base_class_name(provider_name)

        if base_class_name is None:
            # 如果无法推断，尝试从 provider_key 提取
            base_name = provider_key.replace("_provider", "")
            # 常见命名约定映射（兜底方案）
            base_class_map = {
                "cache": "CacheDao",
                "vector": "VectorDao",
                "semantic_cache": "SemanticCache",
                "llm": "BaseLLM",
                "embedder": "BaseEmbedder",
                "classifier": "BaseClassifier",
                "clusterer": "BaseClusterer",
                "sentiment": "BaseSentimentAnalyzer",
                "toxicity": "BaseToxicityDetector",
            }
            base_class_name = base_class_map.get(base_name, base_name)
            logger.warning(
                f"[DependencyInjector] Could not infer base class for {provider_name}, "
                f"using fallback: {base_class_name}"
            )

        self._provider_config[base_class_name] = (provider_name, config_override or {})

        logger.debug(
            f"[DependencyInjector] Configured {base_class_name}: "
            f"provider={provider_name}, config_keys={list((config_override or {}).keys())}"
        )

    def _infer_base_class_name(self, provider_name: str) -> Optional[str]:
        """从 ProviderRegistry 查询 provider 对应的基类名称

        无需硬编码，直接使用注册时自动提取的基类信息。

        Args:
            provider_name: provider 名称（如 'diskcache', 'openai-llm'）

        Returns:
            基类名称（如 'CacheDao', 'BaseLLM'），如果未找到则返回 None
        """
        base_class_name = ProviderRegistry.get_base_class_for_provider(provider_name)
        if base_class_name:
            logger.debug(f"[DependencyInjector] Found mapping: {provider_name} -> {base_class_name}")
        return base_class_name

    def get(self, base_class: Type[T], provider_name: Optional[str] = None, **extra_kwargs) -> T:
        """获取组件实例（自动解析依赖）

        Args:
            base_class: 基类类型
            provider_name: provider 名称（可选，如果已配置则自动使用）
            **extra_kwargs: 额外的构造参数

        Returns:
            实例化的组件

        Example:
            >>> cache = injector.get(SemanticCache)  # 自动解析依赖
            >>> llm = injector.get(BaseLLM, "openai-llm")
        """
        base_class_name = base_class.__name__

        # 1. 确定使用哪个 provider
        resolved_provider_name: str
        if provider_name is None:
            # 从配置中查找
            if base_class_name not in self._provider_config:
                raise ValueError(f"No provider configured for {base_class_name}. Call injector.configure() first.")
            resolved_provider_name, _ = self._provider_config[base_class_name]
        else:
            resolved_provider_name = provider_name

        # 2. 检查缓存（单例）
        cache_key = (base_class, resolved_provider_name)
        if cache_key in self._instance_cache:
            logger.debug(f"[DependencyInjector] Cache hit: {base_class_name}:{resolved_provider_name}")
            return self._instance_cache[cache_key]

        # 3. 检测循环依赖
        resolution_key = f"{base_class_name}:{resolved_provider_name}"
        if resolution_key in self._resolution_stack:
            cycle = " -> ".join(self._resolution_stack + [resolution_key])
            raise ValueError(f"Circular dependency detected: {cycle}")

        self._resolution_stack.append(resolution_key)

        try:
            # 4. 创建实例
            instance = self._create_instance(base_class, resolved_provider_name, extra_kwargs)

            # 5. 缓存实例（如果是单例）
            if ProviderRegistry._singleton_flags.get(resolved_provider_name, True):
                self._instance_cache[cache_key] = instance

            logger.info(f"[DependencyInjector] ✓ Created {base_class_name}:{resolved_provider_name}")
            return instance

        finally:
            self._resolution_stack.pop()

    def _create_instance(self, base_class: Type[T], provider_name: str, extra_kwargs: Dict[str, Any]) -> T:
        """创建实例（自动解析依赖）

        Args:
            base_class: 基类类型
            provider_name: provider 名称
            extra_kwargs: 额外参数

        Returns:
            实例化的组件
        """
        base_class_name = base_class.__name__

        # 1. 获取 provider 类
        provider_class = ProviderRegistry.get(provider_name)
        if provider_class is None:
            raise ValueError(f"Provider not found: {provider_name}")

        # 2. 获取配置覆盖
        _, config_override = self._provider_config.get(base_class_name, (None, {}))

        # 3. 获取构造函数参数
        params_info = ProviderRegistry._params_info.get(provider_name, {})

        # 4. 准备构造参数
        init_kwargs = {}

        for param_name, param_meta in params_info.items():
            if param_name in ["self", "args", "kwargs"]:
                continue

            # 优先级：extra_kwargs > config_override > 依赖注入 > 默认值

            # a) 检查 extra_kwargs
            if param_name in extra_kwargs:
                init_kwargs[param_name] = extra_kwargs[param_name]
                continue

            # b) 检查 config_override
            if param_name in config_override:
                init_kwargs[param_name] = config_override[param_name]
                continue

            # c) 检查是否是依赖注入参数
            param_type = param_meta.get("type")
            if param_type is not None and self._is_dependency_type(param_type):
                # 递归解析依赖
                dependency = self._resolve_dependency(param_type)
                if dependency is not None:
                    init_kwargs[param_name] = dependency
                    logger.debug(f"[DependencyInjector] Injected dependency: {param_name}={type(dependency).__name__}")
                continue

            # d) 使用默认值（如果有）
            default_value = param_meta.get("default")
            is_required = param_meta.get("required", False)

            if is_required and default_value in [None, ..., inspect.Parameter.empty]:
                # 必需参数但没有提供值
                raise ValueError(f"Missing required parameter '{param_name}' for {provider_name}")

            # 跳过可选参数（使用默认值）

        # 5. 使用 ProviderRegistry 创建实例
        try:
            instance = ProviderRegistry.get_instance_from_config(
                base_class, provider_name, config_override=config_override, **init_kwargs
            )
            return instance
        except Exception as e:
            logger.error(f"[DependencyInjector] Failed to create {base_class_name}:{provider_name}: {e}")
            raise

    def _is_dependency_type(self, param_type: Any) -> bool:
        """判断参数类型是否是依赖注入类型

        Args:
            param_type: 参数类型

        Returns:
            是否是依赖类型
        """
        if param_type is None:
            return False

        # 检查是否是类
        if not inspect.isclass(param_type):
            return False

        type_name = param_type.__name__
        module_name = getattr(param_type, "__module__", "")

        # 依赖注入类型的特征：
        # 1. Base* 开头的基类
        # 2. DAO 层类型（CacheDao, VectorDao）
        # 3. SemanticCache
        # 4. CacheTraceRecorder
        # 5. distill_ai/distill_dao 模块的基类
        is_dependency = (
            type_name.startswith("Base")
            or type_name in ["CacheDao", "VectorDao", "SemanticCache", "CacheTraceRecorder"]
            or "distill_dao.base" in module_name
            or "distill_ai.base" in module_name
            or "distill_ai.cache.trace" in module_name
        )

        return is_dependency

    def _resolve_dependency(self, dependency_type: Type) -> Any:
        """解析依赖类型

        Args:
            dependency_type: 依赖类型

        Returns:
            依赖实例
        """
        type_name = dependency_type.__name__

        # 查找是否已配置对应的 provider
        if type_name not in self._provider_config:
            logger.warning(
                f"[DependencyInjector] No provider configured for dependency {type_name}, "
                f"trying to use default provider..."
            )
            # 尝试查找默认 provider
            return self._find_default_provider(dependency_type)

        # 递归调用 get() 解析依赖
        return self.get(dependency_type)

    def _find_default_provider(self, base_class: Type) -> Optional[Any]:
        """查找默认 provider（用于未配置的依赖）

        Args:
            base_class: 基类类型

        Returns:
            默认实例（如果有）
        """
        base_class_name = base_class.__name__
        providers = ProviderRegistry.get_providers_for_base_class(base_class_name)

        if not providers:
            logger.warning(f"[DependencyInjector] No providers found for {base_class_name}")
            return None

        # 使用第一个可用的 provider
        default_provider = providers[0]
        logger.info(f"[DependencyInjector] Using default provider for {base_class_name}: {default_provider}")

        # 自动配置
        self.configure(f"{base_class_name.lower()}_provider", default_provider, {})

        # 递归解析
        return self.get(base_class, default_provider)

    def clear_cache(self):
        """清空实例缓存"""
        self._instance_cache.clear()
        logger.debug("[DependencyInjector] Cache cleared")

    def get_cached_instances(self) -> Dict[str, Any]:
        """获取所有缓存的实例

        Returns:
            实例字典 {class_name:provider_name -> instance}
        """
        result = {}
        for (base_class, provider_name), instance in self._instance_cache.items():
            key = f"{base_class.__name__}:{provider_name}"
            result[key] = instance
        return result


def create_injector_from_config(config: Any) -> DependencyInjector:
    """从配置对象创建依赖注入容器

    Args:
        config: 配置对象（如 PipelineConfig）

    Returns:
        配置好的 DependencyInjector

    Example:
        >>> from distill_etl.dag.assets import PipelineConfig
        >>> config = PipelineConfig(...)
        >>> injector = create_injector_from_config(config)
        >>> cache = injector.get(SemanticCache)
    """
    injector = DependencyInjector()

    # 配置所有 provider - 动态从 config 对象推断
    # 首先获取所有 provider 组
    provider_groups = ProviderRegistry.get_all_provider_groups()

    for base_class_name, config_name in provider_groups.items():
        # 获取配置组
        config_group = getattr(config, config_name, None)
        if not config_group or not isinstance(config_group, dict):
            logger.debug(f"[create_injector_from_config] Skipping {config_name}: config_group not found or not a dict")
            continue

        # 从配置组中获取 provider 名称
        provider_name = config_group.get("provider")
        if not provider_name or provider_name == "":
            logger.debug(f"[create_injector_from_config] Skipping {config_name}: provider not specified")
            continue

        # 获取配置覆盖
        config_override = config_group.get(provider_name, {})

        # 过滤配置中的空字符串字段（通常是依赖注入参数）
        if isinstance(config_override, dict):
            config_override = {k: v for k, v in config_override.items() if v != "" or not isinstance(v, str)}

        # 配置名称作为 attr_name
        attr_name = f"{config_name}_provider"

        # 配置 injector
        injector.configure(attr_name, provider_name, config_override)
        logger.debug(
            f"[create_injector_from_config] Configured {config_name}.provider={provider_name}, "
            f"config_keys={list(config_override.keys())}"
        )

    # 兼容旧格式: 查找所有以 _provider 结尾的属性（如 rdbms_provider）
    config_attrs = dir(config)
    for attr_name in config_attrs:
        if not attr_name.endswith("_provider"):
            continue

        # 跳过已经处理过的配置组
        config_name_prefix = attr_name.replace("_provider", "")
        if config_name_prefix in provider_groups.values():
            continue  # 已经通过 provider 组处理

        provider_name = getattr(config, attr_name, None)
        if not provider_name or provider_name == "":
            continue

        # 获取配置覆盖
        config_override = {}

        # 1. 从 provider 组获取配置名称
        base_class_name = ProviderRegistry.get_base_class_for_provider(provider_name)
        if base_class_name:
            config_name = ProviderRegistry.get_config_name_for_group(base_class_name)
            if config_name:
                config_dict = getattr(config, config_name, {})
                if isinstance(config_dict, dict):
                    config_override = config_dict.get(provider_name, {})

        # 2. 如果没有 provider 组配置，尝试使用 config_path
        if not config_override:
            registered_config_path = ProviderRegistry.get_config_path(provider_name)
            if registered_config_path:
                parts = registered_config_path.split(".")
                if len(parts) >= 2:
                    config_key = parts[0]
                    config_dict = getattr(config, config_key, {})
                    if isinstance(config_dict, dict):
                        config_override = config_dict.get(provider_name, {})

        # 3. 如果还没有找到配置，使用约定
        if not config_override:
            config_key = attr_name.replace("_provider", "_config")
            config_dict = getattr(config, config_key, {})
            config_override = config_dict.get(provider_name, {}) if config_dict else {}

        # 过滤配置中的空字符串字段
        if isinstance(config_override, dict):
            config_override = {k: v for k, v in config_override.items() if v != "" or not isinstance(v, str)}

        # 配置 injector
        injector.configure(attr_name, provider_name, config_override)
        logger.debug(
            f"[create_injector_from_config] Configured {attr_name}={provider_name}, "
            f"config_keys={list(config_override.keys())}"
        )

    return injector
