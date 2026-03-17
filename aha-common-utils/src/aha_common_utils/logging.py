"""日志管理 — 委托至 utils.log（loguru + OpenTelemetry 上下文注入）."""

from __future__ import annotations

from .log import init_logging
from .log import logger as _loguru_logger


def setup_logging(level: str = "INFO", log_dir: str = "logs") -> None:
    """初始化日志系统（loguru，带 OTel trace_id/span_id 注入）."""
    init_logging(level=level, log_dir=log_dir)


def get_logger(name: str | None = None):
    """获取 loguru BoundLogger，并绑定模块名."""
    if name:
        return _loguru_logger.bind(name=name)
    return _loguru_logger
