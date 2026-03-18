"""敏感字段识别常量与工具函数。

独立模块，供 _discovery.py、_base.py 及外部代码直接使用，避免循环依赖。
"""

from __future__ import annotations

__all__ = [
    "SENSITIVE_SUBSTRINGS",
    "INSECURE_DEFAULT_VALUES",
    "is_sensitive_field",
    "mask_value",
]

# 字段名中包含以下任意子串（忽略大小写）时视为敏感字段
SENSITIVE_SUBSTRINGS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "api_key",
        "apikey",
        "token",
        "private_key",
        "access_key",
        "secret_key",
        "dsn",
        "auth",
        "credential",
        "database_url",
        "redis_url",
    }
)

# 生产环境中禁止出现的已知不安全占位值（lowercase 比较）
INSECURE_DEFAULT_VALUES: frozenset[str] = frozenset(
    {
        "change-me-in-production",
        "change_me_in_production",
        "changeme",
        "change_me",
        "secret",
        "password",
        "postgres",
        "admin",
        "your-secret-key",
        "your_secret_key",
        "dev-only",
    }
)


def is_sensitive_field(field_name: str) -> bool:
    """判断字段名是否对应敏感信息（按名称模式匹配）。

    Args:
        field_name: 配置字段名称（大小写不敏感）。

    Returns:
        True 表示该字段可能含密码/密钥等敏感信息。

    Examples:
        >>> is_sensitive_field("DATABASE_URL")
        True
        >>> is_sensitive_field("LOG_LEVEL")
        False
    """
    name_lower = field_name.lower()
    return any(sub in name_lower for sub in SENSITIVE_SUBSTRINGS)


def mask_value(value: object) -> str:
    """将值屏蔽为安全的显示字符串，保留前 4 位便于来源识别。

    Args:
        value: 任意值，会先转为字符串。

    Returns:
        屏蔽后的字符串，如 ``"sk-p****"`` 或 ``"****"``。

    Examples:
        >>> mask_value("sk-proj-abc123")
        'sk-p****'
        >>> mask_value("ab")
        '****'
    """
    s = str(value)
    if not s:
        return repr(value)
    return s[:4] + "****" if len(s) > 4 else "****"
