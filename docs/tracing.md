# 链路追踪（Tracing）使用手册

## 目录

- [概述](#tracing-概述)
- [快速上手](#tracing-快速上手)
- [setup_tracing — 初始化追踪](#setup_tracing--初始化追踪)
- [install_fastapi_trace_middleware — HTTP 请求追踪](#install_fastapi_trace_middleware--http-请求追踪)
- [get_tracer — 获取 Tracer](#get_tracer--获取-tracer)
- [Span 操作参考](#span-操作参考)
- [与日志关联](#与日志关联)
- [与 FastAPI lifespan 完整集成](#与-fastapi-lifespan-完整集成)
- [Tracing 常见问题](#tracing-常见问题)

---

## Tracing 概述

链路追踪模块基于 [OpenTelemetry Python SDK](https://opentelemetry.io/docs/languages/python/) 构建，提供：

- **统一初始化** — 一行代码完成 TracerProvider + OTLP 导出器配置
- **FastAPI 中间件** — 自动为每个 HTTP 请求创建根 Span，命名为 `METHOD /path`
- **日志关联** — trace_id / span_id 自动注入到日志，实现日志与链路的双向关联
- **幂等安装** — 中间件防重复注册，可安全多次调用

---

## Tracing 快速上手

```python
from fastapi import FastAPI
from aha_common_utils.tracing import setup_tracing, install_fastapi_trace_middleware, get_tracer

app = FastAPI()

# 1. 初始化 TracerProvider（应用启动时调用一次）
setup_tracing(
    service_name="my-service",
    otlp_endpoint="http://localhost:4317",
)

# 2. 安装 HTTP 请求自动追踪中间件
install_fastapi_trace_middleware(app)

# 3. 业务代码中手动创建子 Span
tracer = get_tracer(__name__)

def process_order(order_id: str):
    with tracer.start_as_current_span("process_order") as span:
        span.set_attribute("order.id", order_id)
        # ... 业务逻辑
```

---

## setup_tracing — 初始化追踪

```python
from aha_common_utils.tracing import setup_tracing
```

### 函数签名

```python
def setup_tracing(
    service_name: str = "app",
    otlp_endpoint: Optional[str] = None,
    enable_console: bool = False,
) -> trace.Tracer:
    ...
```

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `service_name` | `str` | `"app"` | 服务名称，显示在 Jaeger / Grafana Tempo 等追踪后端中；也会注入到日志的 `otelServiceName` 字段 |
| `otlp_endpoint` | `str \| None` | `None` | OTLP gRPC 导出端点（如 `"http://otel-collector:4317"`）；为 `None` 时不导出 Span |
| `enable_console` | `bool` | `False` | 将 Span 数据打印到控制台，仅用于本地调试 |

### 返回值

返回一个以 `aha_common_utils.tracing` 为 instrumentation 名称的 `trace.Tracer` 实例。

### 调用示例

```python
# 生产：导出到 OTLP Collector
setup_tracing(
    service_name="skillforge-api",
    otlp_endpoint="http://otel-collector:4317",
)

# 开发：打印到控制台（不需要 Collector）
setup_tracing(
    service_name="skillforge-api",
    enable_console=True,
)

# 最小化：仅初始化 Provider（日志中 trace_id / otelServiceName 仍会注入）
setup_tracing(service_name="my-service")
```

---

## install_fastapi_trace_middleware — HTTP 请求追踪

```python
from aha_common_utils.tracing import install_fastapi_trace_middleware
```

### 函数签名

```python
def install_fastapi_trace_middleware(
    app: FastAPI,
    tracer_name: str = "aha_common_utils.tracing",
) -> None:
    ...
```

为 FastAPI 安装请求级 Tracing 中间件。每个 HTTP 请求会自动创建一个根 Span，名称为 `"METHOD /path"`，例如：

```
GET /api/v1/users
POST /api/v1/orders
```

> **幂等保证**：通过 `app.state._trace_middleware_installed` 标记防止重复安装，可以安全多次调用。

---

## get_tracer — 获取 Tracer

```python
from aha_common_utils.tracing import get_tracer

tracer = get_tracer(__name__)
```

### 函数签名

```python
def get_tracer(name: str = "aha_common_utils.tracing") -> trace.Tracer:
    ...
```

获取一个以 `name` 为 instrumentation library 名称的 `Tracer` 实例。业务代码始终传入 `__name__`。

---

## Span 操作参考

### 创建子 Span（同步）

```python
tracer = get_tracer(__name__)

with tracer.start_as_current_span("do_something") as span:
    span.set_attribute("item.id", item_id)
    span.set_attribute("item.count", 10)
    result = do_something()
```

### 创建子 Span（异步）

```python
async def fetch_data(user_id: str):
    with tracer.start_as_current_span("fetch_user_data") as span:
        span.set_attribute("user.id", user_id)
        data = await db.get_user(user_id)
        return data
```

### 记录异常

```python
with tracer.start_as_current_span("risky_operation") as span:
    try:
        result = risky_operation()
    except Exception as e:
        span.record_exception(e)
        span.set_status(trace.StatusCode.ERROR, str(e))
        raise
```

### 添加事件（时间点标记）

```python
with tracer.start_as_current_span("process_batch") as span:
    span.add_event("batch_started", {"batch.size": 100})
    process()
    span.add_event("batch_completed")
```

### 读取当前 Span 的 trace_id / span_id

```python
from opentelemetry.trace import get_current_span

span = get_current_span()
ctx = span.get_span_context()
trace_id = format(ctx.trace_id, "032x")
span_id  = format(ctx.span_id,  "016x")
```

---

## 与日志关联

`setup_tracing()` 初始化后，日志系统（`log.py`）中的 `_add_trace_context` patcher 会自动将当前 Span 的上下文注入到每条日志记录中：

```
2026-03-18 10:23:45.123 | INFO | myapp.api:api.py:process:58 | [trace_id=a1b2c3d4e5f6… span_id=7890abcd…] | 订单处理完成
```

在 Grafana / Jaeger / Tempo 等工具中，可以直接用日志中的 `trace_id` 跳转到对应的完整请求链路。

---

## 与 FastAPI lifespan 完整集成

推荐的完整启动配置（Tracing + Logging + 中间件）：

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from aha_common_utils.logging import setup_logging
from aha_common_utils.tracing import setup_tracing, install_fastapi_trace_middleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 顺序：1. Tracing  2. Logging  3. 中间件
    setup_tracing(
        service_name="skillforge-api",
        otlp_endpoint="http://otel-collector:4317",
    )
    setup_logging(level="INFO", log_dir="logs")
    install_fastapi_trace_middleware(app)
    yield

app = FastAPI(lifespan=lifespan)
```

---

## Tracing 常见问题

### Q: Span 创建了但追踪后端看不到数据？

1. 确认 `otlp_endpoint` 地址正确，Collector 正在监听该端口（默认 `4317`）；
2. 本地调试时设置 `enable_console=True` 确认 Span 是否被正常创建；
3. OTLP 导出器初始化失败时会打印 WARNING 而非抛异常，检查启动日志。

### Q: 开发环境不接追踪后端怎么办？

```python
# 不传 otlp_endpoint，Span 不导出但日志 trace_id 仍正常注入
setup_tracing(service_name="my-service")

# 或打印到终端方便调试
setup_tracing(service_name="my-service", enable_console=True)
```

### Q: 与 `opentelemetry-instrumentation-fastapi` 有冲突吗？

`install_fastapi_trace_middleware` 是手动实现的轻量中间件，与 `FastAPIInstrumentor` 同时使用时会产生两个根 Span。建议二者只选其一；若追求更完整的属性覆盖（HTTP 状态码、路由参数等），推荐使用官方 `FastAPIInstrumentor`。

### Q: `setup_tracing` 的返回值和 `get_tracer()` 有什么区别？

`setup_tracing` 返回以 `aha_common_utils.tracing` 为 instrumentation 名称的 Tracer；`get_tracer(__name__)` 返回以调用方模块名为 instrumentation 名称的 Tracer。功能完全相同，区别仅在于追踪 UI 中显示的 instrumentation library 标签。业务代码统一使用 `get_tracer(__name__)` 即可。
