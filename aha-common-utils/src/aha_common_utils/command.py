from typing import Any


def extract_value(param_value: Any, param_default=None) -> Any:
    """从typer.Option对象中提取实际值"""
    if hasattr(param_value, 'default'):
        # 这是一个typer.Option对象
        return param_value.default if param_value.default is not ... else param_default
    return param_value
