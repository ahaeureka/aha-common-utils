"""组件装配日志不得打印参数**值**（敏感值尤其）。

## 背景（实测缺陷）

``ClassFactory.get_instance`` 在过滤出构造参数后打了一行调试日志：

```python
logger.debug(f"Filtered kwargs for {impl.__name__}: {filtered_kwargs}")
```

``filtered_kwargs`` 是 **name → value**，于是装配任何组件都会把它的完整构造参数写进日志。
实测在 qunapai 里跑一次只读 CLI 就会带出 Redis 密码与 LLM/Embedding 的 API key：

```text
Filtered kwargs for RedisRDBMSImpl: {'url': 'redis://:hunter2@127.0.0.1:6379/2', 'pool_size': 10}
```

## 本文件锁定的契约

1. **按名字识别敏感参数**：复用共享库既有的 ``is_sensitive_field`` + ``mask_value``
   （``config_base`` 里已用于 ``BaseParameters.__repr__``），不为日志另造一套规则；
2. **按内容识别凭据型 URL**：``redis://:pass@host`` 这类把凭据写在 userinfo 里的 DSN，
   键名可能叫 ``url`` / ``endpoint``（**不含**任何敏感子串），只按名字判会漏。
   这种值必须把 userinfo 换成 ``****``；
3. **诊断能力不能一起删掉**：非敏感的键仍然要能看见（值或键名），否则日志失去意义。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from aha_common_utils.register import register_provider
from aha_common_utils.runtime.provider_registry import create_provider_instance
from loguru import logger as _loguru_logger

#: 敏感值用不可能自然出现的标记串，避免断言被别的日志巧合满足。
SECRET_PASSWORD = "hunter2-LEAK-CANARY"
SECRET_API_KEY = "sk-live-LEAKCANARY-0123456789"
SECRET_TOKEN = "tok-LEAKCANARY-abcdef"
REDIS_DSN = f"redis://:{SECRET_PASSWORD}@127.0.0.1:6379/2"

PROVIDER_NAME = "logging-redaction-fixture"


class FakePort:
    """被装配的端口：构造函数参数名刻意覆盖「按名字能识别」与「识别不了」两类。"""

    def __init__(
        self,
        url: str = "",
        password: str = "",
        api_key: str = "",
        token: str = "",
        pool_size: int = 5,
    ) -> None:
        self.url = url
        self.password = password
        self.api_key = api_key
        self.token = token
        self.pool_size = pool_size


@register_provider(PROVIDER_NAME, singleton=False)
class FakeImpl(FakePort):
    """注册进注册表的实现（非单例，避免影响其它用例）。"""


@contextmanager
def captured_log_messages(level: str = "DEBUG") -> Iterator[list[str]]:
    """收集 loguru 的**消息文本**（不是 record repr）。

    共享库的 ``get_logger`` 返回 loguru logger，``caplog``（stdlib）看不到它。
    """
    messages: list[str] = []
    handler_id = _loguru_logger.add(messages.append, level=level, format="{message}")
    try:
        yield messages
    finally:
        _loguru_logger.remove(handler_id)


def _instantiate(**parameters: Any) -> str:
    """按 provider 名构造实例并返回**全部日志文本**（含默认 sink 之外的部分）。"""
    with captured_log_messages() as messages:
        create_provider_instance(PROVIDER_NAME, FakePort, parameters=parameters)

    return "\n".join(messages)


def test_sensitive_parameter_values_never_reach_the_log() -> None:
    """按名字能识别的敏感参数：原始值不得出现在任何日志行里。"""
    text = _instantiate(
        url="http://example.invalid/api",
        password=SECRET_PASSWORD,
        api_key=SECRET_API_KEY,
        token=SECRET_TOKEN,
        pool_size=7,
    )

    assert SECRET_PASSWORD not in text
    assert SECRET_API_KEY not in text
    assert SECRET_TOKEN not in text


def test_credentialed_url_is_masked_even_under_a_non_sensitive_name() -> None:
    """键名不含敏感子串的凭据型 DSN 同样必须脱敏。

    ``url`` 不是敏感字段名，但它的值里带着密码 —— 只按名字判会把它整条打进日志。
    """
    text = _instantiate(url=REDIS_DSN, pool_size=7)

    assert SECRET_PASSWORD not in text
    assert "127.0.0.1:6379/2" in text or "****" in text, "脱敏后仍应能看出是哪个端点"


def test_non_sensitive_parameters_stay_visible() -> None:
    """脱敏不能把诊断能力一起删掉：非敏感参数的键与值仍要看得见。"""
    text = _instantiate(url="http://example.invalid/api", pool_size=7)

    assert "pool_size" in text
    assert "7" in text
    assert "http://example.invalid/api" in text or "****" in text


def test_masking_is_visible_as_masking_not_silent_removal() -> None:
    """日志要**显示被打码**（``****``），而不是把字段整个删掉 —— 否则读日志的人会以为参数没传。"""
    text = _instantiate(password=SECRET_PASSWORD)

    assert "password" in text
    assert "****" in text


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql+asyncpg://qunapai:pw@127.0.0.1:5432/qunapai_dev",
        "redis://:pw@127.0.0.1:6379/0",
        "https://bearer-token@api.example.com/v1",
    ],
)
def test_dsn_userinfo_is_masked_regardless_of_scheme(dsn: str) -> None:
    """三种真实形态（用户密码 / 只密码 / 只 token）都要被识别。"""
    text = _instantiate(url=dsn)

    assert "pw@" not in text
    assert "bearer-token@" not in text
