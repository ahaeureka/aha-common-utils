"""
OpenTelemetry 追踪配置模块

为中间件和pipeline提供统一的追踪功能
"""

from collections.abc import Awaitable, Callable
from typing import Optional

from fastapi import FastAPI, Request, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .logging import get_logger

logger = get_logger(__name__)


def setup_tracing(
    service_name: str = "app",
    otlp_endpoint: Optional[str] = None,
    enable_console: bool = False,
) -> trace.Tracer:
    """
    配置OpenTelemetry追踪

    Args:
        service_name: 服务名称
        otlp_endpoint: OTLP导出端点 (例如: "http://localhost:4317")
        enable_console: 是否启用控制台导出器（用于调试）

    Returns:
        配置好的Tracer实例
    """
    # 创建资源
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": "0.1.0",
        }
    )

    # 创建TracerProvider
    provider = TracerProvider(resource=resource)

    # 添加OTLP导出器
    if otlp_endpoint:
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info(f"OpenTelemetry OTLP导出器已配置: {otlp_endpoint}")
        except Exception as e:
            logger.warning(f"配置OTLP导出器失败: {e}")

    # 添加控制台导出器（用于调试）
    if enable_console:
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(console_exporter))
        logger.info("OpenTelemetry控制台导出器已启用")

    # 设置全局TracerProvider
    trace.set_tracer_provider(provider)

    # 返回tracer
    tracer = trace.get_tracer(__name__)

    logger.info(f"OpenTelemetry追踪已初始化: {service_name}")
    return tracer


def install_fastapi_trace_middleware(app: FastAPI, tracer_name: str = __name__) -> None:
    """为 FastAPI 安装请求级 tracing 中间件（幂等）."""
    if getattr(app.state, "_trace_middleware_installed", False):
        return

    tracer = trace.get_tracer(tracer_name)

    @app.middleware("http")
    async def _trace_request(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        span_name = f"{request.method} {request.url.path}"
        with tracer.start_as_current_span(span_name):
            response = await call_next(request)
            return response

    app.state._trace_middleware_installed = True


def get_tracer(name: str = __name__) -> trace.Tracer:
    """
    获取Tracer实例

    Args:
        name: tracer名称，通常使用模块名

    Returns:
        Tracer实例
    """
    return trace.get_tracer(name)
