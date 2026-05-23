"""aha_common_utils.cli — 类 FastAPI 风格的声明式 CLI 框架。

基于 typer 封装，提供 FastAPI 风格的参数注解和子命令管理，支持两级子命令
（CliApp → Router → command）和 async def 自动包装。

Quick Start::

    from typing import Annotated
    from aha_common_utils.cli import CliApp, Router, Opt, Arg, EnvOpt, SecretOpt, FlagOpt

    app = CliApp(name="myapp", help="示例应用", no_args_is_help=True)

    db = Router(name="db", help="数据库命令")

    @db.command("upgrade")
    async def db_upgrade(
        url: Annotated[str, EnvOpt("DATABASE_URL", help="DB 连接 URL")],
        dry_run: Annotated[bool, FlagOpt(help="仅预览", short="-n")] = False,
    ):
        \"\"\"升级数据库 schema。\"\"\"
        ...

    @db.command("init")
    def db_init(
        password: Annotated[str, SecretOpt(help="DB 密码", envvar="DB_PASSWORD")],
    ): ...

    app.include_router(db)

    @app.command("serve")
    def serve(
        host: Annotated[str, Opt(help="绑定地址", envvar="HOST")] = "0.0.0.0",
        port: Annotated[int, Opt(help="端口", short="-p")] = 8080,
        verbose: Annotated[bool, FlagOpt(help="详细输出", short="-v")] = False,
        name: Annotated[str, Arg(help="服务名称")],
    ): ...

    app.run()
"""

from __future__ import annotations

from ._app import CliApp, Router
from ._params import Arg, EnvOpt, FlagOpt, Opt, SecretOpt

__all__ = [
    # 应用与路由
    "CliApp",
    "Router",
    # 参数注解助手
    "Opt",
    "Arg",
    "EnvOpt",
    "SecretOpt",
    "FlagOpt",
]
