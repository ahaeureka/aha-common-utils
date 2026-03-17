"""配置文件解析工具

提供通用的配置文件解析功能，支持 YAML/TOML/JSON 格式。
供 ConfigLoader 和 ProviderRegistry 等模块复用。

新增功能：
1. 环境变量加载（支持 .env 文件）
2. 基于前缀的环境变量过滤和解析
3. 动态创建 pydantic BaseSettings 配置类
4. 环境变量与配置路径绑定
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Type, TypeVar

from .logging import get_logger

T = TypeVar("T")

logger = get_logger(__name__)


def parse_config_file(config_file: str | Path) -> Dict[str, Any]:
    """解析配置文件

    Args:
        config_file: 配置文件路径（支持 .yaml/.yml/.toml/.json）

    Returns:
        配置字典

    Raises:
        ValueError: 不支持的文件格式或文件不存在
        Exception: 文件解析错误

    Examples:
        >>> config = parse_config_file("config.yaml")
        >>> config = parse_config_file("/app/config.toml")
        >>> config = parse_config_file("settings.json")
    """
    # 检查文件是否存在
    if not os.path.exists(config_file):
        raise ValueError(f"Config file not found: {config_file}")

    file_path = Path(config_file)
    suffix = file_path.suffix.lower()

    # 读取并解析配置文件
    if suffix in [".yaml", ".yml"]:
        return _parse_yaml(config_file)
    elif suffix == ".toml":
        return _parse_toml(config_file)
    elif suffix == ".json":
        return _parse_json(config_file)
    else:
        raise ValueError(f"Unsupported config file format: {suffix}. Supported: .yaml, .yml, .toml, .json")


def extract_nested_config(config_data: Dict[str, Any], config_path: str) -> Dict[str, Any]:
    """从配置字典中提取嵌套配置

    根据点分隔的路径提取配置，如 "cache.diskcache" 会提取
    config_data["cache"]["diskcache"]

    Args:
        config_data: 配置字典
        config_path: 配置路径（如 "cache.diskcache"）

    Returns:
        提取的配置字典，如果路径不存在返回空字典

    Examples:
        >>> config = {"cache": {"diskcache": {"dir": "/tmp"}}}
        >>> extract_nested_config(config, "cache.diskcache")
        {'dir': '/tmp'}
    """
    result = config_data
    for key in config_path.split("."):
        if isinstance(result, dict) and key in result:
            result = result[key]
        else:
            logger.warning(f"Config path '{config_path}' not found in config data")
            return {}

    if not isinstance(result, dict):
        logger.warning(f"Config at path '{config_path}' is not a dict")
        return {}

    return result


def load_config_section(config_file: str | Path, config_path: str) -> Dict[str, Any]:
    """加载配置文件中的指定配置段

    组合了 parse_config_file 和 extract_nested_config 的功能。

    Args:
        config_file: 配置文件路径
        config_path: 配置路径（如 "cache.diskcache"）

    Returns:
        提取的配置字典

    Raises:
        ValueError: 文件不存在或格式不支持

    Examples:
        >>> config = load_config_section("config.yaml", "cache.diskcache")
        >>> # 等价于先解析文件，再提取路径
    """
    config_data = parse_config_file(config_file)
    return extract_nested_config(config_data, config_path)


def _parse_yaml(config_file: str | Path) -> Dict[str, Any]:
    """解析 YAML 配置文件"""
    try:
        import yaml

        with open(config_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        raise ValueError("PyYAML is not installed. Install it with: pip install pyyaml")


def _parse_toml(config_file: str | Path) -> Dict[str, Any]:
    """解析 TOML 配置文件"""
    try:
        import tomli

        with open(config_file, "rb") as f:
            return tomli.load(f)
    except ImportError:
        try:
            import toml

            with open(config_file, "r", encoding="utf-8") as f:
                return toml.load(f)
        except ImportError:
            raise ValueError("TOML parser not installed. Install with: pip install tomli (or toml)")


def _parse_json(config_file: str | Path) -> Dict[str, Any]:
    """解析 JSON 配置文件"""
    import json

    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# 环境变量加载功能
# ============================================================================


def load_env_file(env_file: Optional[Path] = None, override: bool = False) -> None:
    """加载 .env 文件到环境变量

    Args:
        env_file: .env 文件路径，默认为 /app/.env
        override: 是否覆盖已存在的环境变量，默认为 False

    Note:
        如果已经安装了 python-dotenv，会使用它来加载
        否则使用简单的解析器

    Examples:
        >>> load_env_file(Path("/app/.env"))
        >>> load_env_file(Path("config/.env"), override=True)
    """
    if env_file is None:
        env_file = Path("/app/.env")

    if not env_file.exists():
        logger.debug(f"Env file not found: {env_file}")
        return

    try:
        # 尝试使用 python-dotenv（推荐）
        from dotenv import load_dotenv

        load_dotenv(env_file, override=override)
        logger.debug(f"Loaded env file using python-dotenv: {env_file}")
    except ImportError:
        # 如果没有安装 python-dotenv，使用简单解析
        _simple_load_env(env_file, override=override)
        logger.debug(f"Loaded env file using simple parser: {env_file}")


def _simple_load_env(env_file: Path, override: bool = False) -> None:
    """简单的 .env 文件解析器（当 python-dotenv 不可用时）

    Args:
        env_file: .env 文件路径
        override: 是否覆盖已存在的环境变量
    """
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # 跳过注释和空行
            if not line or line.startswith("#"):
                continue
            # 解析 KEY=VALUE
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                # 移除引号
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                # 设置环境变量
                if override or key not in os.environ:
                    os.environ[key] = value


def get_env_with_prefix(
    prefix: str,
    case_sensitive: bool = False,
    strip_prefix: bool = True,
) -> Dict[str, str]:
    """获取带指定前缀的环境变量

    Args:
        prefix: 环境变量前缀（如 'ETL_', 'CACHE_'）
        case_sensitive: 是否区分大小写
        strip_prefix: 是否从键名中移除前缀

    Returns:
        环境变量字典

    Examples:
        >>> # ETL_LLM_PROVIDER=openai-llm
        >>> # ETL_BATCH_SIZE=100
        >>> env_vars = get_env_with_prefix("ETL_")
        >>> # {'llm_provider': 'openai-llm', 'batch_size': '100'}

        >>> # CACHE_ENABLED=true
        >>> # CACHE_TTL=3600
        >>> cache_vars = get_env_with_prefix("CACHE_", strip_prefix=False)
        >>> # {'CACHE_ENABLED': 'true', 'CACHE_TTL': '3600'}
    """
    result = {}

    for key, value in os.environ.items():
        # 检查前缀匹配
        if case_sensitive:
            if not key.startswith(prefix):
                continue
            result_key = key[len(prefix):] if strip_prefix else key
        else:
            if not key.upper().startswith(prefix.upper()):
                continue
            result_key = key[len(prefix):] if strip_prefix else key

        # 转换为小写（如果不区分大小写）
        if not case_sensitive:
            result_key = result_key.lower()

        result[result_key] = value

    return result


def parse_env_value(value: str) -> Any:
    """解析环境变量值为合适的类型

    Args:
        value: 环境变量字符串值

    Returns:
        解析后的值（bool, int, float, str）

    Examples:
        >>> parse_env_value("true")  # True
        >>> parse_env_value("100")  # 100
        >>> parse_env_value("30.5")  # 30.5
        >>> parse_env_value("hello")  # 'hello'
    """
    # 布尔值
    if value.lower() in ("true", "yes", "1", "on"):
        return True
    if value.lower() in ("false", "no", "0", "off"):
        return False

    # 数字
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    # 字符串
    return value


def env_key_to_config_path(env_key: str, separator: str = "__") -> str:
    """将环境变量键名转换为配置路径

    Args:
        env_key: 环境变量键名(如 'llm_config__openai_llm__api_key')
        separator: 层级分隔符(默认 '__',双下划线)

    Returns:
        配置路径(如 'llm_config.openai-llm.api_key')

    Examples:
        >>> env_key_to_config_path("llm_config__openai_llm__api_key")
        'llm_config.openai-llm.api_key'

        >>> env_key_to_config_path("batch_size")
        'batch_size'

        >>> env_key_to_config_path("llm_provider")
        'llm_provider'
    """
    # 替换双下划线为点号
    path = env_key.replace(separator, ".")

    # 将单下划线转换为连字符(仅针对 provider 名称部分)
    # 规则: 如果一个部分同时包含字母和下划线,且看起来像 provider 名称,则转换
    # 例如: openai_llm, text_embedder -> openai-llm, text-embedder
    # 但不转换: llm_config, api_key -> llm_config, api_key (保持原样)
    parts = path.split(".")
    normalized_parts = []

    for part in parts:
        # 检查是否需要转换为连字符
        # 判断依据:
        # 1. 包含下划线
        # 2. 不是常见的配置键名(如 api_key, model_name 等)
        # 3. 看起来像 provider 名称（通常是 <type>_<name> 形式）
        should_convert = False

        if "_" in part:
            # 排除常见的配置键名模式
            common_patterns = [
                "config",
                "key",
                "name",
                "size",
                "timeout",
                "url",
                "host",
                "port",
                "mode",
                "level",
                "params",
                "path",
                "file",
                "dir",
                "api",
                "model",
                "max",
                "min",
            ]
            is_config_key = any(pattern in part for pattern in common_patterns)

            # 检查是否看起来像 provider 名称
            # Provider 通常是: <type>_<name> 形式,如 openai_llm, text_embedder
            has_two_parts = len(part.split("_")) >= 2

            # 如果不是配置键名,且有两个或更多部分,则转换
            if not is_config_key and has_two_parts:
                should_convert = True

        if should_convert:
            normalized_parts.append(part.replace("_", "-"))
        else:
            normalized_parts.append(part)

    return ".".join(normalized_parts)


def set_nested_value(config: Dict[str, Any], path: str, value: Any) -> None:
    """设置嵌套字典中的值

    Args:
        config: 配置字典
        path: 点号分隔的路径(如 'llm_config.openai-llm.api_key')
        value: 要设置的值

    Examples:
        >>> config = {}
        >>> set_nested_value(config, "llm_config.openai-llm.api_key", "sk-xxx")
        >>> # config = {'llm_config': {'openai-llm': {'api_key': 'sk-xxx'}}}
    """
    parts = path.split(".")
    current = config

    # 遍历路径,创建中间字典
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        elif not isinstance(current[part], dict):
            # 如果中间路径不是字典,无法继续
            return
        current = current[part]

    # 设置最终值
    current[parts[-1]] = value


def apply_env_to_config(
    config: Dict[str, Any],
    env_prefix: str,
    case_sensitive: bool = False,
) -> Dict[str, Any]:
    """将环境变量应用到配置字典(支持嵌套路径)

    Args:
        config: 原始配置字典
        env_prefix: 环境变量前缀
        case_sensitive: 是否区分大小写

    Returns:
        合并后的配置字典

    Examples:
        >>> # 平铺配置
        >>> # 环境变量: ETL_LLM_PROVIDER=openai-llm
        >>> config = {"llm_provider": "default-llm"}
        >>> result = apply_env_to_config(config, "ETL_")
        >>> # {'llm_provider': 'openai-llm'}  # 环境变量覆盖

        >>> # 嵌套配置(使用双下划线分隔层级)
        >>> # 环境变量: ETL_LLM_CONFIG__OPENAI_LLM__API_KEY=sk-xxx
        >>> config = {}
        >>> result = apply_env_to_config(config, "ETL_")
        >>> # {'llm_config': {'openai-llm': {'api_key': 'sk-xxx'}}}

    Note:
        环境变量命名规则:
        - 使用双下划线 '__' 分隔嵌套层级
        - 单下划线 '_' 会自动转换为连字符 '-'(provider 命名)
        - 示例:ETL_LLM_CONFIG__OPENAI_LLM__API_KEY
          -> llm_config.openai-llm.api_key
    """
    env_vars = get_env_with_prefix(env_prefix, case_sensitive)

    # 深拷贝配置
    import copy

    result = copy.deepcopy(config)

    # 应用环境变量（环境变量优先）
    for key, value in env_vars.items():
        # 解析值类型
        parsed_value = parse_env_value(value)

        # 转换为配置路径
        config_path = env_key_to_config_path(key)

        # 设置值(支持嵌套)
        if "." in config_path:
            set_nested_value(result, config_path, parsed_value)
        else:
            result[config_path] = parsed_value

    return result


# ============================================================================
# Pydantic BaseSettings 动态创建
# ============================================================================


def create_settings_class(
    class_name: str,
    config_path: str,
    fields_spec: Dict[str, Any],
    env_prefix: str = "",
    case_sensitive: bool = False,
) -> Type:
    """动态创建 pydantic BaseSettings 配置类

    Args:
        class_name: 配置类名称
        config_path: 配置路径（如 'cache.diskcache'）
        fields_spec: 字段规范字典 {field_name: (type, default_value)}
        env_prefix: 环境变量前缀
        case_sensitive: 是否区分大小写

    Returns:
        动态创建的 BaseSettings 类

    Examples:
        >>> fields = {
        ...     "api_key": (str, "default-key"),
        ...     "timeout": (int, 30),
        ...     "enabled": (bool, True),
        ... }
        >>> SettingsClass = create_settings_class("OpenAIConfig", "llm.openai", fields, env_prefix="OPENAI_")
        >>> settings = SettingsClass()
        >>> # 自动从环境变量 OPENAI_API_KEY, OPENAI_TIMEOUT 等加载配置
    """
    try:
        from pydantic_settings import BaseSettings, SettingsConfigDict
    except ImportError:
        raise ImportError(
            "pydantic-settings is required for this feature. Install it with: pip install pydantic-settings"
        )

    # 构建字段字典
    annotations = {}
    defaults = {}

    for field_name, field_spec in fields_spec.items():
        if isinstance(field_spec, tuple):
            field_type, default_value = field_spec
        else:
            field_type = field_spec
            default_value = None

        annotations[field_name] = field_type
        if default_value is not None:
            defaults[field_name] = default_value

    # 创建配置字典
    config_dict = SettingsConfigDict(
        env_prefix=env_prefix,
        case_sensitive=case_sensitive,
        env_nested_delimiter="__",
        extra="allow",  # 允许额外字段
    )

    # 动态创建类
    namespace = {
        "__annotations__": annotations,
        "model_config": config_dict,
        "__module__": __name__,
        "__doc__": f"Settings for {config_path}",
        **defaults,
    }

    settings_class = type(class_name, (BaseSettings,), namespace)
    return settings_class


def load_config_with_env(
    config_file: Optional[Path] = None,
    config_path: Optional[str] = None,
    env_file: Optional[Path] = None,
    env_prefix: str = "",
    case_sensitive: bool = False,
) -> Dict[str, Any]:
    """加载配置文件并应用环境变量覆盖

    Args:
        config_file: 配置文件路径（可选）
        config_path: 配置路径（如 'cache.diskcache'）
        env_file: .env 文件路径（可选）
        env_prefix: 环境变量前缀
        case_sensitive: 是否区分大小写

    Returns:
        合并后的配置字典

    Examples:
        >>> # 从文件加载并应用环境变量
        >>> config = load_config_with_env(
        ...     config_file=Path("config.yaml"), config_path="cache.redis", env_prefix="REDIS_"
        ... )

        >>> # 仅从环境变量加载
        >>> config = load_config_with_env(env_prefix="CACHE_")
    """
    # 加载 .env 文件
    if env_file:
        load_env_file(env_file)

    # 加载配置文件
    base_config = {}
    if config_file:
        if config_path:
            base_config = load_config_section(config_file, config_path)
        else:
            base_config = parse_config_file(config_file)

    # 应用环境变量
    if env_prefix:
        return apply_env_to_config(base_config, env_prefix, case_sensitive)

    return base_config


__all__ = [
    # 配置文件解析
    "parse_config_file",
    "extract_nested_config",
    "load_config_section",
    # 环境变量加载
    "load_env_file",
    "get_env_with_prefix",
    "parse_env_value",
    "env_key_to_config_path",
    "set_nested_value",
    "apply_env_to_config",
    # Pydantic Settings
    "create_settings_class",
    "load_config_with_env",
]
