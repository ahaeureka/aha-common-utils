"""配置注册系统

提供配置注册装饰器和注册表管理，支持：
1. 每个 package 独立定义配置类
2. 通过装饰器注册配置项
3. 支持嵌套配置和主配置标记
4. 配置类与加载器解耦
"""
from typing import Any, Callable, Dict, Optional, Type, TypeVar

from pydantic_settings import BaseSettings

T = TypeVar('T', bound=BaseSettings)


class ConfigRegistry:
    """配置注册表

    管理所有注册的配置类，支持嵌套配置和主配置。
    """

    def __init__(self):
        """初始化配置注册表"""
        self._configs: Dict[str, Type[BaseSettings]] = {}
        self._main_config: Optional[str] = None
        self._config_metadata: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: str,
        config_class: Type[T],
        is_main: bool = False,
        description: Optional[str] = None,
        depends_on: Optional[list[str]] = None,
    ) -> Type[T]:
        """注册配置类

        Args:
            name: 配置名称（用于标识和嵌套）
            config_class: 配置类（必须继承自 BaseSettings）
            is_main: 是否为主配置（每个应用只能有一个主配置）
            description: 配置描述
            depends_on: 依赖的其他配置名称列表

        Returns:
            原配置类（不修改）

        Raises:
            ValueError: 如果配置名称重复或主配置重复
        """
        if name in self._configs:
            raise ValueError(f"配置 '{name}' 已经注册")

        if is_main:
            if self._main_config is not None:
                raise ValueError(
                    f"主配置已存在: {self._main_config}，"
                    f"不能注册多个主配置（尝试注册: {name}）"
                )
            self._main_config = name

        self._configs[name] = config_class
        self._config_metadata[name] = {
            'is_main': is_main,
            'description': description,
            'depends_on': depends_on or [],
            'class': config_class,
        }

        return config_class

    def get_config(self, name: str) -> Optional[Type[BaseSettings]]:
        """获取已注册的配置类

        Args:
            name: 配置名称

        Returns:
            配置类，如果不存在返回 None
        """
        return self._configs.get(name)

    def get_main_config(self) -> Optional[Type[BaseSettings]]:
        """获取主配置类

        Returns:
            主配置类，如果没有注册主配置返回 None
        """
        if self._main_config:
            return self._configs.get(self._main_config)
        return None

    def get_main_config_name(self) -> Optional[str]:
        """获取主配置名称

        Returns:
            主配置名称，如果没有注册主配置返回 None
        """
        return self._main_config

    def list_configs(self) -> Dict[str, Dict[str, Any]]:
        """列出所有已注册的配置

        Returns:
            配置元数据字典
        """
        return self._config_metadata.copy()

    def has_main_config(self) -> bool:
        """检查是否已注册主配置

        Returns:
            True 如果已注册主配置
        """
        return self._main_config is not None

    def clear(self) -> None:
        """清除所有注册的配置（主要用于测试）"""
        self._configs.clear()
        self._main_config = None
        self._config_metadata.clear()


# 全局配置注册表实例
_global_registry = ConfigRegistry()


def register_config(
    name: str,
    is_main: bool = False,
    description: Optional[str] = None,
    depends_on: Optional[list[str]] = None,
) -> Callable[[Type[T]], Type[T]]:
    """配置注册装饰器

    将配置类注册到全局注册表，支持嵌套配置和主配置标记。

    Args:
        name: 配置项名称（用于标识和嵌套引用）
        is_main: 是否为主配置（整个应用只能有一个主配置）
        description: 配置描述信息
        depends_on: 依赖的其他配置名称列表（用于配置依赖管理）

    Returns:
        装饰器函数

    Examples:
        >>> from pydantic_settings import BaseSettings
        >>> from distill_utils.config import register_config

        >>> # 注册子配置
        >>> @register_config("database", description="数据库配置")
        >>> class DatabaseSettings(BaseSettings):
        ...     host: str = "localhost"
        ...     port: int = 5432

        >>> # 注册另一个子配置
        >>> @register_config("llm", description="LLM配置")
        >>> class LLMSettings(BaseSettings):
        ...     model_name: str = "gpt-3.5-turbo"
        ...     api_key: str = ""

        >>> # 注册主配置（依赖前面的子配置）
        >>> @register_config("app", is_main=True, depends_on=["database", "llm"])
        >>> class AppSettings(BaseSettings):
        ...     app_name: str = "my-app"
        ...     database: DatabaseSettings
        ...     llm: LLMSettings
    """
    def decorator(config_class: Type[T]) -> Type[T]:
        return _global_registry.register(
            name=name,
            config_class=config_class,
            is_main=is_main,
            description=description,
            depends_on=depends_on,
        )
    return decorator


def get_registry() -> ConfigRegistry:
    """获取全局配置注册表

    Returns:
        全局配置注册表实例
    """
    return _global_registry


def get_config_class(name: str) -> Optional[Type[BaseSettings]]:
    """获取已注册的配置类

    Args:
        name: 配置名称

    Returns:
        配置类，如果不存在返回 None
    """
    return _global_registry.get_config(name)


def get_main_config_class() -> Optional[Type[BaseSettings]]:
    """获取主配置类

    Returns:
        主配置类，如果没有注册主配置返回 None
    """
    return _global_registry.get_main_config()


__all__ = [
    'ConfigRegistry',
    'register_config',
    'get_registry',
    'get_config_class',
    'get_main_config_class',
]
