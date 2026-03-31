# 日志系统使用手册

## 目录

- [概述](#日志概述)
- [快速上手](#日志快速上手)
- [初始化 init_logging / setup_logging](#初始化-init_logging--setup_logging)
- [获取 Logger](#获取-logger)
- [日志级别](#日志级别)
- [携带业务 extra 字段](#携带业务-extra-字段)
- [请求 ID 注入](#请求-id-注入)
- [日志输出格式](#日志输出格式)
- [日志文件轮转](#日志文件轮转)
- [OpenTelemetry 上下文自动注入](#opentelemetry-上下文自动注入)
- [与 FastAPI lifespan 集成](#与-fastapi-lifespan-集成)
- [日志常见问题](#日志常见问题)

---

## 日志概述

日志系统基于 [Loguru](https://github.com/Delgan/loguru) 构建，并自动注入 [OpenTelemetry](https://opentelemetry.io/) 的 `trace_id` / `span_id`，实现日志与链路追踪的天然关联。核心特性：

- **结构化格式** — 每行日志包含时间、级别、模块位置、trace/span ID、消息
- **OTel 上下文自动注入** — 日志自动携带当前活跃 Span 的 trace_id 和 span_id
- **双路输出** — 同时输出到 stderr（带颜色）和日志文件（纯文本）
- **日志文件轮转** — 按天轮转，自动压缩，错误日志单独存档
- **业务 extra 字段** — 支持在日志中携带任意业务 KV 信息
- **多进程安全** — 文件写入使用 `enqueue=True`

---

## 日志快速上手

```python
# 1. 应用启动时初始化（只需调用一次）
from aha_common_utils.logging import setup_logging

setup_logging(level="INFO", log_dir="logs")

# 2. 各模块中获取 logger
from aha_common_utils.logging import get_logger

logger = get_logger(__name__)

# 3. 记录日志
logger.info("应用启动成功")
logger.debug("调试信息")
logger.warning("注意事项")
logger.error("发生错误")
logger.critical("严重故障")
```

---

## 初始化 init_logging / setup_logging

```python
from aha_common_utils.log import init_logging
# 或等价的高层封装：
from aha_common_utils.logging import setup_logging
```

### 函数签名

```python
def init_logging(level: str = "DEBUG", log_dir: str = "logs") -> None: ...
def setup_logging(level: str = "INFO", log_dir: str = "logs") -> None: ...
```

`setup_logging` 是 `init_logging` 的高层封装，默认级别为 `"INFO"`；`init_logging` 默认级别为 `"DEBUG"`。

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `level` | `str` | `"INFO"` / `"DEBUG"` | 日志最低输出级别 |
| `log_dir` | `str` | `"logs"` | 日志文件输出目录；传空字符串 `""` 则仅输出到控制台 |

### 调用示例

```python
# 仅输出到控制台（不写文件）
setup_logging(level="DEBUG", log_dir="")

# 输出到控制台 + logs/ 目录
setup_logging(level="INFO", log_dir="logs")

# 输出到自定义目录
setup_logging(level="WARNING", log_dir="/var/log/myapp")
```

> **注意**：`init_logging` / `setup_logging` 不会在模块加载时自动调用，必须在应用启动阶段显式调用一次。

---

## 获取 Logger

```python
from aha_common_utils.logging import get_logger

# 推荐：传入模块名，日志来源字段显示为准确的模块路径
logger = get_logger(__name__)

# 不传名称时使用全局 loguru logger
logger = get_logger()
```

`get_logger(__name__)` 与直接使用 `from loguru import logger` 的区别：前者将 `__name__` 绑定为 `extra["name"]` 字段，日志中的 `name` 字段会显示为调用方模块路径，而非 loguru 内部模块名。

---

## 日志级别

| 级别 | 方法 | 适用场景 |
|------|------|----------|
| `TRACE` | `logger.trace()` | 极细粒度调试（默认不显示） |
| `DEBUG` | `logger.debug()` | 开发调试信息 |
| `INFO` | `logger.info()` | 正常运行流程事件 |
| `SUCCESS` | `logger.success()` | 操作成功（Loguru 特有） |
| `WARNING` | `logger.warning()` | 非预期但可恢复的情况 |
| `ERROR` | `logger.error()` | 发生错误，需关注 |
| `CRITICAL` | `logger.critical()` | 严重故障，系统不可用 |

各环境建议级别：

| 环境 | 推荐级别 |
|------|---------|
| `development` | `DEBUG` |
| `test` | `WARNING` |
| `production` | `INFO` 或 `WARNING` |

---

## 携带业务 extra 字段

Loguru 支持在单次日志调用或绑定时携带任意 KV 字段，这些字段会出现在日志行末尾（`| key='value' ...` 格式）：

```python
# 方式 1：bind() 创建绑定了字段的子 logger，适合请求级上下文
request_logger = logger.bind(user_id="u-123", request_id="r-abc")
request_logger.info("开始处理请求")
request_logger.info("请求处理完成")

# 方式 2：单条日志绑定
logger.bind(order_id="o-789", amount=99.9).info("订单创建成功")
```

输出示例：

```
2026-03-18 10:23:45.123 | INFO | myapp:api.py:handle:42 | [trace_id=abc span_id=def] | 订单创建成功 | amount=99.9 order_id='o-789'
```

内部保留字段（`name`、`otelSpanID`、`otelTraceID` 等）会被自动过滤，不出现在 `businessExtra` 中。

---

## 请求 ID 注入

日志模块暴露了 `request_id_var`（`ContextVar[str]`），供中间件注入请求级追踪 ID。当 OTel 无活跃 Span 时，`otelTraceID` 字段会回退使用此值：

```python
from aha_common_utils.log import request_id_var
import uuid

# 在 HTTP 中间件中注入
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    token = request_id_var.set(req_id)
    try:
        return await call_next(request)
    finally:
        request_id_var.reset(token)
```

---

## 日志输出格式

```
2026-03-18 10:23:45.123 | INFO     | myapp.api:api.py:handle:42 | [trace_id=abc123… span_id=def456…] | 请求处理完成 | order_id='o-789'
```

| 字段 | 说明 |
|------|------|
| 时间戳 | 毫秒精度 |
| 级别 | 右对齐 8 位 |
| `name:file:function:line` | 模块名、文件名、函数名、行号 |
| `trace_id` | OTel trace ID（无活跃 Span 时为 `0` 或 request_id） |
| `span_id` | OTel span ID（无活跃 Span 时为 `0`） |
| 消息 | 日志文本 |
| `businessExtra` | 业务 KV 字段（有则追加 `\| key=value …`，无则省略） |

---

## 日志文件轮转

`init_logging` 在 `log_dir` 下创建两类日志文件：

| 文件名模式 | 最低级别 | 轮转时间 | 保留时长 | 压缩格式 |
|-----------|---------|---------|---------|---------|
| `app_YYYY-MM-DD.log` | ≥ `level` 参数 | 每天 00:00 | 30 天 | zip |
| `error_YYYY-MM-DD.log` | ERROR+ | 每天 00:00 | 7 天 | zip |

文件写入使用 `enqueue=True`，保证多进程/多线程安全。

---

## OpenTelemetry 上下文自动注入

日志模块在每条记录写入前，通过 Loguru 的 `patcher` 机制自动注入以下字段：

| 字段 | 来源 | 说明 |
|------|------|------|
| `otelTraceID` | 当前活跃 OTel Span | 32 位十六进制 |
| `otelSpanID` | 当前活跃 OTel Span | 16 位十六进制 |
| `otelTraceSampled` | 当前活跃 OTel Span | 是否被采样 |
| `otelServiceName` | TracerProvider resource | 服务名称 |

无活跃 Span 时，`otelTraceID` 回退到 `request_id_var` 注入的值；若两者均无，显示为 `"0"`。

---

## 与 FastAPI lifespan 集成

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from aha_common_utils.logging import setup_logging

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(level="INFO", log_dir="logs")
    yield

app = FastAPI(lifespan=lifespan)
```

---

## 日志常见问题

### Q: 日志中 trace_id 一直显示 0？

说明没有活跃的 OTel Span 且 `request_id_var` 未注入。确保已调用 `setup_tracing()` 并安装了请求追踪中间件（见下方 Tracing 手册）。

### Q: 如何关闭文件日志输出？

```python
setup_logging(level="DEBUG", log_dir="")
```

### Q: 如何在测试中屏蔽所有日志输出？

```python
import loguru
loguru.logger.disable("")   # 禁用所有模块的日志
```

### Q: 多次调用 setup_logging 会怎样？

Loguru 的 `logger.remove()` 在 `init_logging` 内部每次都会清除已有 handler 再重新添加，多次调用是安全的，但会导致之前自定义的 handler 丢失。建议只在应用启动时调用一次。

---
