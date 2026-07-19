"""aha_common_utils.cli._params — 类 FastAPI 风格的 CLI 参数注解助手。

提供 Opt、Arg、EnvOpt、SecretOpt、FlagOpt 五个函数，返回 typer 的
OptionInfo / ArgumentInfo 对象，可直接用于 Annotated[T, Opt(...)] 语法。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import typer


def _normalize_envvar(envvar: str | Sequence[str] | None) -> str | list[str] | None:
    if envvar is None or isinstance(envvar, str):
        return envvar
    return list(envvar)


def Opt(
    *,
    help: str = "",
    envvar: str | Sequence[str] | None = None,
    short: str | None = None,
    show_default: bool = True,
    hidden: bool = False,
    prompt: bool | str = False,
    confirmation_prompt: bool = False,
    metavar: str | None = None,
    show_envvar: bool = True,
    **kwargs: Any,
) -> Any:
    """通用选项注解助手，对应 typer.Option。

    Args:
        help: 帮助文本。
        envvar: 绑定的环境变量名，可为字符串或字符串列表。
        short: 短选项，如 ``"-v"``、``"-p"``；会追加到 param_decls。
        show_default: 是否在 help 中显示默认值。
        hidden: 是否在 --help 中隐藏该选项。
        prompt: 为 True 时交互提示输入；也可传自定义提示文字。
        confirmation_prompt: 是否要求二次确认（常与 prompt 配合）。
        metavar: 在 usage 行中显示的值占位符。
        show_envvar: 是否在 help 中展示环境变量名。
        **kwargs: 直接透传给 typer.Option 的其余参数。

    Returns:
        typer.OptionInfo，可用于 ``Annotated[T, Opt(...)]``。

    Examples:
        >>> host: Annotated[str, Opt(help="绑定地址", envvar="HOST")] = "0.0.0.0"
        >>> port: Annotated[int, Opt(help="端口", short="-p")] = 8080
    """
    param_decls: list[str] = []
    if short:
        param_decls.append(short)

    return typer.Option(
        *param_decls,
        help=help,
        envvar=_normalize_envvar(envvar),
        show_default=show_default,
        hidden=hidden,
        prompt=prompt,
        confirmation_prompt=confirmation_prompt,
        metavar=metavar,
        show_envvar=show_envvar,
        **kwargs,
    )


def Arg(
    *,
    help: str = "",
    metavar: str | None = None,
    show_default: bool = True,
    hidden: bool = False,
    **kwargs: Any,
) -> Any:
    """位置参数注解助手，对应 typer.Argument。

    Args:
        help: 帮助文本。
        metavar: 在 usage 行中显示的值占位符。
        show_default: 是否在 help 中显示默认值。
        hidden: 是否在 --help 中隐藏该参数。
        **kwargs: 直接透传给 typer.Argument 的其余参数。

    Returns:
        typer.ArgumentInfo，可用于 ``Annotated[T, Arg(...)]``。

    Examples:
        >>> name: Annotated[str, Arg(help="服务名称")]
    """
    return typer.Argument(
        help=help,
        metavar=metavar,
        show_default=show_default,
        hidden=hidden,
        **kwargs,
    )


def EnvOpt(
    envvar: str,
    *,
    help: str = "",
    short: str | None = None,
    show_default: bool = True,
    hidden: bool = False,
    metavar: str | None = None,
    show_envvar: bool = True,
    **kwargs: Any,
) -> Any:
    """强制绑定环境变量的选项注解助手。

    第一个位置参数为环境变量名，确保该参数一定会从指定环境变量读取值。
    等同于 ``Opt(envvar=envvar, ...)``，但更突显环境变量绑定意图。

    Args:
        envvar: 必填，绑定的环境变量名，如 ``"DATABASE_URL"``。
        help: 帮助文本。
        short: 短选项，如 ``"-u"``。
        show_default: 是否在 help 中显示默认值。
        hidden: 是否在 --help 中隐藏该选项。
        metavar: 在 usage 行中显示的值占位符。
        show_envvar: 是否在 help 中展示环境变量名。
        **kwargs: 直接透传给 typer.Option 的其余参数。

    Returns:
        typer.OptionInfo，可用于 ``Annotated[T, EnvOpt("ENV_VAR", help=...)]``。

    Examples:
        >>> url: Annotated[str, EnvOpt("DATABASE_URL", help="数据库连接 URL")]
    """
    param_decls: list[str] = []
    if short:
        param_decls.append(short)

    return typer.Option(
        *param_decls,
        help=help,
        envvar=_normalize_envvar(envvar),
        show_default=show_default,
        hidden=hidden,
        metavar=metavar,
        show_envvar=show_envvar,
        **kwargs,
    )


def SecretOpt(
    *,
    help: str = "",
    envvar: str | Sequence[str] | None = None,
    short: str | None = None,
    prompt: bool | str = True,
    confirmation_prompt: bool = False,
    metavar: str | None = None,
    **kwargs: Any,
) -> Any:
    """密码/密钥输入选项注解助手。

    自动启用 ``hide_input=True``。当 ``envvar`` 已设置时，typer 会优先读取
    环境变量而跳过交互提示；未设置环境变量时才进行交互输入。

    Args:
        help: 帮助文本。
        envvar: 绑定的环境变量名，有此值时跳过交互提示。
        short: 短选项。
        prompt: 交互提示文字，默认为 True（显示字段名作为提示）。
        confirmation_prompt: 是否要求二次确认。
        metavar: 在 usage 行中显示的值占位符。
        **kwargs: 直接透传给 typer.Option 的其余参数。

    Returns:
        typer.OptionInfo，可用于 ``Annotated[str, SecretOpt(envvar="DB_PASSWORD")]``。

    Examples:
        >>> password: Annotated[str, SecretOpt(help="数据库密码", envvar="DB_PASSWORD")]
    """
    param_decls: list[str] = []
    if short:
        param_decls.append(short)

    return typer.Option(
        *param_decls,
        help=help,
        envvar=_normalize_envvar(envvar),
        hide_input=True,
        prompt=prompt,
        confirmation_prompt=confirmation_prompt,
        metavar=metavar,
        **kwargs,
    )


def FlagOpt(
    *,
    help: str = "",
    short: str | None = None,
    hidden: bool = False,
    **kwargs: Any,
) -> Any:
    """布尔开关选项注解助手。

    专为 ``bool`` 类型设计，typer 会自动生成 ``--flag / --no-flag`` 对。
    当提供 ``short`` 时，将其追加到 param_decls 作为短选项（对应正向 flag）。

    Args:
        help: 帮助文本。
        short: 短选项，如 ``"-v"``、``"-n"``（对应正向布尔值）。
        hidden: 是否在 --help 中隐藏。
        **kwargs: 直接透传给 typer.Option 的其余参数。

    Returns:
        typer.OptionInfo，可用于 ``Annotated[bool, FlagOpt(help="...", short="-v")]``。

    Examples:
        >>> verbose: Annotated[bool, FlagOpt(help="详细输出", short="-v")] = False
        >>> dry_run: Annotated[bool, FlagOpt(help="仅预览", short="-n")] = False
    """
    param_decls: list[str] = []
    if short:
        param_decls.append(short)

    return typer.Option(
        *param_decls,
        help=help,
        hidden=hidden,
        is_flag=True,
        **kwargs,
    )
