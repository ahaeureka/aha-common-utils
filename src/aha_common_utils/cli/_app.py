"""aha_common_utils.cli._app — CliApp 与 Router，类 FastAPI 风格的 typer 封装。

设计约束：
- 两级子命令（CliApp → Router → command），Router 不可再嵌套
- async def 函数自动用 asyncio.run 包装，用户无需关心同步/异步区别
- API 命名刻意对齐 FastAPI：include_router、callback、command
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from typing import Any, Callable, TypeVar

import typer

F = TypeVar("F", bound=Callable[..., Any])


# ── 内部工具 ──────────────────────────────────────────────────────────────────


def _wrap_async(fn: F) -> F:
    """若 fn 是协程函数，返回用 asyncio.run 包装的同步版本；否则返回原函数。

    包装后的函数保留原函数的 __name__、__doc__ 和 __wrapped__ 属性，
    以确保 typer 能正确生成 help 文本和命令名称。

    Args:
        fn: 待包装的函数，可以是同步或异步函数。

    Returns:
        同步可调用对象。typer 不支持 async，经此包装后均可安全注册。
    """
    if not inspect.iscoroutinefunction(fn):
        return fn

    @functools.wraps(fn)
    def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(fn(*args, **kwargs))

    return _sync_wrapper  # type: ignore[return-value]


# ── Router ────────────────────────────────────────────────────────────────────


class Router:
    """子命令组，对应 FastAPI 的 APIRouter。

    封装一个命名的 typer.Typer 实例，提供与 CliApp 一致的
    .command() / .callback() 装饰器接口，支持 async def。

    通过 ``CliApp.include_router(router)`` 将子命令组挂载到主应用。

    Attributes:
        name: 子命令组名称，用作 CLI 中的子命令前缀（如 ``myapp db ...``）。
        help: 子命令组的帮助文本，显示在 ``myapp --help`` 的子命令列表中。
    """

    def __init__(
        self,
        name: str,
        *,
        help: str = "",
        no_args_is_help: bool = True,
        deprecated: bool = False,
    ) -> None:
        """初始化子命令组。

        Args:
            name: 子命令组名称。
            help: 帮助文本。
            no_args_is_help: 无参数调用时是否打印 help（默认 True）。
            deprecated: 标记为已废弃，会在 help 中显示 "(deprecated)"。
        """
        self.name = name
        self.help = help
        self._typer = typer.Typer(
            name=name,
            help=help,
            no_args_is_help=no_args_is_help,
            deprecated=deprecated,
        )

    def command(
        self,
        name: str | None = None,
        *,
        help: str | None = None,
        deprecated: bool = False,
        no_args_is_help: bool = False,
        hidden: bool = False,
    ) -> Callable[[F], F]:
        """注册子命令装饰器，支持 async def。

        Args:
            name: 命令名称；省略时使用函数名（下划线转连字符）。
            help: 命令帮助文本；省略时使用函数 docstring。
            deprecated: 标记为已废弃。
            no_args_is_help: 无参数时打印 help。
            hidden: 在 help 列表中隐藏该命令。

        Returns:
            装饰器函数。

        Examples:
            >>> @router.command("upgrade")
            ... async def upgrade(url: Annotated[str, EnvOpt("DATABASE_URL")]): ...
        """

        def decorator(fn: F) -> F:
            wrapped = _wrap_async(fn)
            self._typer.command(
                name=name,
                help=help,
                deprecated=deprecated,
                no_args_is_help=no_args_is_help,
                hidden=hidden,
            )(wrapped)
            return fn  # 返回原始函数，方便在其他地方直接调用

        return decorator

    def callback(
        self,
        *,
        invoke_without_command: bool = False,
        no_args_is_help: bool = False,
    ) -> Callable[[F], F]:
        """注册组级回调（共享选项），在任意子命令执行前调用，支持 async def。

        常用于为整个命令组添加通用参数（如 ``--verbose``、``--config``）。

        Args:
            invoke_without_command: 无子命令时是否仍调用 callback。
            no_args_is_help: 无参数时打印 help。

        Returns:
            装饰器函数。

        Examples:
            >>> @db.callback()
            ... def db_common(verbose: Annotated[bool, FlagOpt()] = False): ...
        """

        def decorator(fn: F) -> F:
            wrapped = _wrap_async(fn)
            self._typer.callback(
                invoke_without_command=invoke_without_command,
                no_args_is_help=no_args_is_help,
            )(wrapped)
            return fn

        return decorator


# ── CliApp ────────────────────────────────────────────────────────────────────


class CliApp:
    """CLI 主应用，对应 FastAPI 的 FastAPI()。

    封装顶层 typer.Typer 实例，提供 .command()、.include_router()、
    .callback() 和 .run() 接口，支持 async def 命令函数。

    Attributes:
        name: CLI 程序名称，显示在 --help 的 Usage 行。
        help: 顶层帮助文本。
    """

    def __init__(
        self,
        name: str | None = None,
        *,
        help: str = "",
        no_args_is_help: bool = True,
        add_completion: bool = True,
    ) -> None:
        """初始化 CLI 主应用。

        Args:
            name: 程序名称；省略时由 typer 从调用入口自动推断。
            help: 顶层帮助文本，显示在 ``myapp --help``。
            no_args_is_help: 无参数调用时打印 help（默认 True）。
            add_completion: 是否添加 shell 补全命令（``--install-completion`` 等）。
        """
        self.name = name
        self.help = help
        self._typer = typer.Typer(
            name=name,
            help=help,
            no_args_is_help=no_args_is_help,
            add_completion=add_completion,
        )

    def command(
        self,
        name: str | None = None,
        *,
        help: str | None = None,
        deprecated: bool = False,
        no_args_is_help: bool = False,
        hidden: bool = False,
    ) -> Callable[[F], F]:
        """注册顶层命令装饰器，支持 async def。

        Args:
            name: 命令名称；省略时使用函数名（下划线转连字符）。
            help: 帮助文本；省略时使用函数 docstring。
            deprecated: 标记为已废弃。
            no_args_is_help: 无参数时打印 help。
            hidden: 在 help 列表中隐藏该命令。

        Returns:
            装饰器函数。

        Examples:
            >>> @app.command("serve")
            ... def serve(host: Annotated[str, Opt(envvar="HOST")] = "0.0.0.0"): ...
        """

        def decorator(fn: F) -> F:
            wrapped = _wrap_async(fn)
            self._typer.command(
                name=name,
                help=help,
                deprecated=deprecated,
                no_args_is_help=no_args_is_help,
                hidden=hidden,
            )(wrapped)
            return fn

        return decorator

    def include_router(
        self,
        router: Router,
        *,
        prefix: str | None = None,
        help: str | None = None,
        deprecated: bool = False,
    ) -> None:
        """挂载子命令组，对应 FastAPI 的 include_router。

        Args:
            router: 要挂载的 Router 实例。
            prefix: 覆盖 router 的名称作为子命令前缀；省略时使用 router.name。
            help: 覆盖 router 的帮助文本；省略时使用 router.help。
            deprecated: 标记整个子命令组为已废弃。

        Examples:
            >>> app.include_router(db)
            >>> app.include_router(db, prefix="database", help="数据库管理命令")
        """
        self._typer.add_typer(
            router._typer,
            name=prefix if prefix is not None else router.name,
            help=help if help is not None else router.help or None,
            deprecated=deprecated,
        )

    def callback(
        self,
        *,
        invoke_without_command: bool = False,
        no_args_is_help: bool = False,
    ) -> Callable[[F], F]:
        """注册顶层回调，常用于添加全局选项（如 ``--version``），支持 async def。

        Args:
            invoke_without_command: 无子命令时是否仍调用 callback。
            no_args_is_help: 无参数时打印 help。

        Returns:
            装饰器函数。

        Examples:
            >>> @app.callback()
            ... def main(version: Annotated[bool, FlagOpt(help="显示版本")] = False):
            ...     if version:
            ...         typer.echo("1.0.0")
            ...         raise typer.Exit()
        """

        def decorator(fn: F) -> F:
            wrapped = _wrap_async(fn)
            self._typer.callback(
                invoke_without_command=invoke_without_command,
                no_args_is_help=no_args_is_help,
            )(wrapped)
            return fn

        return decorator

    def run(self, args: list[str] | None = None) -> None:
        """启动 CLI 应用。

        Args:
            args: 传入的参数列表；为 None 时 typer 自动读取 ``sys.argv[1:]``。
                  主要用于测试场景显式传参。

        Examples:
            >>> app.run()  # 正常 CLI 入口
            >>> app.run(["serve", "myapp", "-p", "9000"])  # 测试时显式传参
        """
        self._typer(args=args, standalone_mode=True)
