"""参数扫描和配置生成器

扫描类的 __init__ 方法参数，提取类型注解和 ParamMeta 元数据，
并动态生成 pydantic BaseSettings 配置类。
"""

import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, get_args, get_origin, get_type_hints

from pydantic import Field
from pydantic_settings import BaseSettings

from .logging import get_logger
from .param_metadata import ParamMeta

logger = get_logger(__name__)


def _find_env_files() -> List[Path]:
    """递归查找所有 .env 文件，从当前目录向上直到根目录的 pyproject.toml

    优先级：内层 > 外层
    返回的列表按照 Pydantic 加载顺序排列（先加载的优先级低）

    Returns:
        .env 文件路径列表，从外层到内层排序
    """
    env_files = []
    current = Path.cwd().resolve()
    root_pyproject = None

    # 第一遍：向上查找，记录所有 .env 和 pyproject.toml
    visited = []
    while True:
        env_file = current / ".env"
        if env_file.exists():
            visited.append(("env", current, env_file))

        pyproject = current / "pyproject.toml"
        if pyproject.exists():
            visited.append(("pyproject", current, pyproject))
            root_pyproject = current

        # 检查是否到达文件系统根目录
        parent = current.parent
        if parent == current:
            break
        current = parent

    # 第二遍：从最外层的 pyproject.toml 向下收集 .env
    if root_pyproject:
        for item_type, path, file in reversed(visited):
            if item_type == "env" and path >= root_pyproject:
                env_files.append(file)
    else:
        # 如果没找到 pyproject.toml，收集所有 .env
        for item_type, path, file in reversed(visited):
            if item_type == "env":
                env_files.append(file)

    if env_files:
        logger.debug(f"[ConfigGenerator] Found .env files (outer→inner): {[str(f) for f in env_files]}")

    return env_files


class ParamScanner:
    """参数扫描器 - 扫描类的 __init__ 参数"""

    @staticmethod
    def scan_init_params(cls: Type) -> Dict[str, Dict[str, Any]]:
        """扫描类的 __init__ 参数（仅扫描带 ParamMeta 注解的配置参数）

        Args:
            cls: 要扫描的类

        Returns:
            参数信息字典，格式: {
                "param_name": {
                    "type": 参数类型,
                    "default": 默认值,
                    "meta": ParamMeta 元数据对象,
                    "required": 是否必填,
                    "annotation": 原始类型注解
                }
            }

        Note:
            只有包含 ParamMeta 注解的参数才会被识别为配置项，
            其他参数被视为依赖注入参数，不会出现在生成的配置类中。
        """
        params_info = {}

        try:
            # 获取 __init__ 方法签名
            sig = inspect.signature(cls.__init__)
            # 获取类型注解
            type_hints = get_type_hints(cls.__init__, include_extras=True)

            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue

                # 提取类型和元数据
                annotation = type_hints.get(param_name, param.annotation)
                param_type, param_meta = ParamScanner._extract_type_and_meta(annotation)

                # 只处理带 ParamMeta 注解的参数（配置项）
                if param_meta is None:
                    logger.debug(
                        f"[ParamScanner] {cls.__name__}.{param_name}: "
                        f"Skipped (no ParamMeta, treated as dependency injection parameter)"
                    )
                    continue

                # 确定默认值
                default_value = param.default if param.default is not inspect.Parameter.empty else ...

                # 如果有 ParamMeta，优先使用其 default
                if param_meta.default is not ...:
                    default_value = param_meta.default

                params_info[param_name] = {
                    "type": param_type,
                    "default": default_value,
                    "meta": param_meta,
                    "required": default_value is ...,
                    "annotation": annotation,
                }

                logger.debug(
                    f"[ParamScanner] {cls.__name__}.{param_name}: "
                    f"type={param_type}, default={default_value}, required={default_value is ...}, "
                    f"meta={param_meta.description if param_meta else None}"
                )

        except Exception as e:
            logger.warning(f"[ParamScanner] Failed to scan {cls.__name__}.__init__: {e}")

        return params_info

    @staticmethod
    def scan_all_params(cls: Type) -> Dict[str, Dict[str, Any]]:
        """扫描类的 __init__ 方法的所有参数（包括依赖注入参数）

        与 scan_init_params 不同，此方法扫描所有参数，不过滤 ParamMeta。
        用于依赖注入系统识别依赖类型。

        Args:
            cls: 要扫描的类

        Returns:
            参数信息字典，格式：
            {
                "param_name": {
                    "type": 实际类型,
                    "default": 默认值,
                    "meta": ParamMeta 元数据对象（如果有）,
                    "required": 是否必填,
                    "annotation": 原始类型注解
                }
            }
        """
        params_info = {}

        try:
            # 获取 __init__ 方法签名
            sig = inspect.signature(cls.__init__)
            # 获取类型注解
            type_hints = get_type_hints(cls.__init__, include_extras=True)

            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue

                # 提取类型和元数据
                annotation = type_hints.get(param_name, param.annotation)
                param_type, param_meta = ParamScanner._extract_type_and_meta(annotation)

                # 确定默认值
                default_value = param.default if param.default is not inspect.Parameter.empty else ...

                # 如果有 ParamMeta，优先使用其 default
                if param_meta and param_meta.default is not ...:
                    default_value = param_meta.default

                params_info[param_name] = {
                    "type": param_type,
                    "default": default_value,
                    "meta": param_meta,
                    "required": default_value is ...,
                    "annotation": annotation,
                }

                logger.debug(
                    f"[ParamScanner.scan_all_params] {cls.__name__}.{param_name}: "
                    f"type={param_type}, default={default_value}, required={default_value is ...}, "
                    f"has_meta={param_meta is not None}"
                )

        except Exception as e:
            logger.warning(f"[ParamScanner] Failed to scan all params of {cls.__name__}.__init__: {e}")

        return params_info

    @staticmethod
    def _extract_type_and_meta(annotation: Any) -> tuple[Any, Optional[ParamMeta]]:
        """从类型注解中提取类型和 ParamMeta

        Args:
            annotation: 类型注解，可能是 Annotated[type, ParamMeta(...)]

        Returns:
            (实际类型, ParamMeta对象或None)
        """
        # 检查是否是 Annotated 类型
        origin = get_origin(annotation)

        if origin is not None:
            # Python 3.9+ typing.Annotated
            from typing import Annotated

            if origin is Annotated:
                args = get_args(annotation)
                if args:
                    actual_type = args[0]
                    # 查找 ParamMeta 实例
                    for metadata in args[1:]:
                        if isinstance(metadata, ParamMeta):
                            return actual_type, metadata
                    return actual_type, None

        # 不是 Annotated 类型，直接返回
        return annotation, None


class ConfigClassGenerator:
    """配置类生成器 - 动态生成 BaseSettings 配置类"""

    @staticmethod
    def generate_config_class(
        provider_name: str,
        config_path: str,
        params_info: Dict[str, Dict[str, Any]],
    ) -> Type[BaseSettings]:
        """生成 pydantic BaseSettings 配置类

        Args:
            provider_name: provider 名称
            config_path: 配置路径，如 "cache.diskcache"
            params_info: 参数信息字典（来自 ParamScanner.scan_init_params）

        Returns:
            动态生成的 BaseSettings 子类

        Examples:
            >>> params = {
            ...     "directory": {
            ...         "type": str,
            ...         "default": ".cache",
            ...         "meta": ParamMeta(description="缓存目录"),
            ...         "required": False,
            ...     },
            ...     "size_limit": {
            ...         "type": int,
            ...         "default": 1073741824,
            ...         "meta": ParamMeta(description="缓存大小限制", ge=0),
            ...         "required": False,
            ...     },
            ... }
            >>> ConfigClass = ConfigClassGenerator.generate_config_class("diskcache", "cache.diskcache", params)
        """
        # 构建字段定义
        fields = {}
        annotations = {}

        for param_name, param_info in params_info.items():
            param_type = param_info["type"]
            default_value = param_info["default"]
            param_meta = param_info["meta"]

            # 构建 Field 参数
            field_kwargs = {}
            if param_meta:
                field_kwargs = param_meta.to_field_info()

            # 设置默认值
            if default_value is not ...:
                if "default" not in field_kwargs:
                    field_kwargs["default"] = default_value
            else:
                # 必填字段，使用 ... 作为 default
                field_kwargs["default"] = ...

            # 注意：不需要设置 alias，Pydantic Settings 会自动使用字段名

            # 创建 Field
            fields[param_name] = Field(**field_kwargs)
            annotations[param_name] = param_type

        # 生成类名
        class_name = f"{provider_name.replace('-', '_').title()}Config"

        # 构建 model_config
        env_prefix = config_path.replace(".", "__").upper() + "__"

        # 递归查找所有 .env 文件
        env_files = _find_env_files()

        # 动态创建类
        namespace = {
            "__annotations__": annotations,
            "model_config": {
                "env_prefix": env_prefix,
                "env_nested_delimiter": "__",
                "case_sensitive": False,
                "extra": "ignore",
                # 支持多个 .env 文件，按优先级加载（内层覆盖外层）
                "env_file": env_files if env_files else None,
                "env_file_encoding": "utf-8",
            },
            **fields,
        }

        # 创建配置类
        config_cls = type(class_name, (BaseSettings,), namespace)

        logger.debug(
            f"[ConfigClassGenerator] Generated {class_name} with prefix {env_prefix}, fields: {list(fields.keys())}"
        )

        return config_cls

    @staticmethod
    def generate_nested_config(
        config_path: str,
        params_info: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """生成嵌套配置字典（用于 YAML/TOML）

        Args:
            config_path: 配置路径，如 "cache.diskcache"
            params_info: 参数信息字典

        Returns:
            嵌套配置字典，例如:
            {
                "cache": {
                    "diskcache": {
                        "directory": ".cache",
                        "size_limit": 1073741824
                    }
                }
            }
        """
        # 构建配置值
        config_values = {}
        for param_name, param_info in params_info.items():
            default_value = param_info["default"]
            if default_value is not ...:
                config_values[param_name] = default_value

        # 按路径构建嵌套结构
        path_parts = config_path.split(".")
        result = config_values

        for part in reversed(path_parts):
            result = {part: result}

        return result
