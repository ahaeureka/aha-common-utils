import sys
from contextvars import ContextVar
from pathlib import Path

from loguru import logger
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.trace import (
    INVALID_SPAN,
    INVALID_SPAN_CONTEXT,
    get_current_span,
    get_tracer_provider,
)

LoggingInstrumentor().instrument(set_logging_format=True)


_INTERNAL_EXTRA_KEYS = {
    "name",
    "otelSpanID",
    "otelTraceID",
    "otelTraceSampled",
    "otelServiceName",
    "businessExtra",
}


def _format_business_extra(extra: dict) -> str:
    """格式化业务 extra 字段，避免内部观测字段污染输出。"""
    items: list[str] = []
    for key in sorted(extra):
        if key in _INTERNAL_EXTRA_KEYS:
            continue
        items.append(f"{key}={extra[key]!r}")
    if not items:
        return ""
    return " | " + " ".join(items)


# 每次 gRPC 请求的链路 ID（由拦截器注入）。
# 优先使用网关传入的 x-request-id，否则在拦截器中自动生成 UUID。
request_id_var: ContextVar[str] = ContextVar("glimmer_request_id", default="")


def _add_trace_context(record):
    """为日志记录添加 OpenTelemetry 跟踪上下文"""
    # 初始化默认值
    record["extra"]["otelSpanID"] = "0"
    record["extra"]["otelTraceID"] = "0"
    record["extra"]["otelTraceSampled"] = False
    record["extra"]["otelServiceName"] = ""

    # 获取服务名称
    try:
        provider = get_tracer_provider()
        resource = getattr(provider, "resource", None)
        if resource:
            service_name = resource.attributes.get("service.name", "")
            record["extra"]["otelServiceName"] = service_name
    except Exception as e:
        logger.warning(f"Failed to get service name from tracer provider resource: {e}")

    # 优先使用 OTel span 的 trace 上下文
    span = get_current_span()
    if span != INVALID_SPAN:
        ctx = span.get_span_context()
        if ctx != INVALID_SPAN_CONTEXT:
            record["extra"]["otelSpanID"] = format(ctx.span_id, "016x")
            record["extra"]["otelTraceID"] = format(ctx.trace_id, "032x")
            record["extra"]["otelTraceSampled"] = ctx.trace_flags.sampled

    # 若 OTel 无活跃 span，则回退到 gRPC 拦截器注入的 request_id
    if record["extra"]["otelTraceID"] == "0":
        req_id = request_id_var.get()
        if req_id:
            record["extra"]["otelTraceID"] = req_id

    record["extra"]["businessExtra"] = _format_business_extra(record["extra"])


def init_logging(level="DEBUG", log_dir="logs"):
    """项目全局日志初始化，只需调用一次."""

    # 配置 OpenTelemetry 跟踪上下文注入
    logger.configure(patcher=_add_trace_context)

    # 移除默认的stderr处理器
    logger.remove()

    # 自定义格式（包含 OpenTelemetry 跟踪信息）
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{file}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "[trace_id={extra[otelTraceID]} span_id={extra[otelSpanID]}] | "
        "<level>{message}</level>{extra[businessExtra]}"
    )

    # 控制台输出配置（带颜色）
    logger.add(
        sys.stderr,
        colorize=True,
        format=log_format,
        level=level,
        backtrace=True,
        diagnose=True,
    )
    if log_dir:
        # 文件输出格式（无颜色标签）
        file_format = (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{file}:{function}:{line} | "
            "[trace_id={extra[otelTraceID]} span_id={extra[otelSpanID]}] | "
            "{message}{extra[businessExtra]}"
        )

        # 文件输出配置
        logger.add(
            Path(log_dir) / "app_{time:YYYY-MM-DD}.log",
            rotation="00:00",  # 每天午夜轮转
            retention="30 days",
            compression="zip",
            format=file_format,
            level=level,
            enqueue=True,  # 多进程安全
        )

        # 单独的错误日志
        logger.add(
            Path(log_dir) / "error_{time:YYYY-MM-DD}.log",
            rotation="00:00",
            retention="7 days",
            level="ERROR",
            format=file_format,
            compression="zip",
        )


# 注意：init_logging() 不在模块加载时自动调用，
# 请在应用启动时显式调用（如在 lifespan 中）。
