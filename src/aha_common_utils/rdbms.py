#!/usr/bin/env python
"""
@File    :   rdbms.py
@Time    :   2024/07/04 17:22:52
@Desc    : Enhanced RDBMS class with port interface implementation
@Updated :   2025/06/22 - Added DatabaseSessionPort interface support
"""

import json
import logging
from contextlib import asynccontextmanager
from typing import TypeVar

import sqlalchemy
import sqlalchemy.exc
import tenacity
from pydantic import BaseModel
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.engine.cursor import CursorResult
from sqlalchemy.engine.result import Result
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Executable
from sqlmodel import SQLModel, select, update
from tenacity import retry, stop_after_attempt, wait_fixed

logging.basicConfig()
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

TSQLModel = TypeVar("TSQLModel", bound="SQLModel")


class JSONSerializer:
    def serializer(self, value):
        if isinstance(value, BaseModel) or isinstance(value, SQLModel):
            return json.dumps(value.model_dump(), ensure_ascii=False)
        if isinstance(value, list):
            return json.dumps(
                [v.model_dump() if isinstance(v, BaseModel) or isinstance(v, SQLModel) else v for v in value],
                ensure_ascii=False,
            )
        return json.dumps(value, ensure_ascii=False)

    def deserializer(self, value):
        return json.loads(value)


class RDBMS:
    """
    Enhanced RDBMS class implementing DatabaseSessionPort interface.
    Manages database sessions with transaction support and retry logic.

    Features:
    - Transaction context manager support
    - Health check mechanism
    - Automatic retry on operational errors
    - Integration with DatabaseSessionPort interface
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize RDBMS with an existing AsyncSession instance.

        For new code, prefer using begin_tx() method to create sessions.
        """
        self._session = session

    async def begin_tx(self) -> AsyncSession:
        """Begin and return a new transaction session.

        This method is part of the DatabaseSessionPort interface.
        """
        return self._session

    async def commit_tx(self, session: AsyncSession) -> None:
        """Commit the transaction.

        This method is part of the DatabaseSessionPort interface.
        """
        await session.commit()

    async def rollback_tx(self, session: AsyncSession) -> None:
        """Rollback the transaction.

        This method is part of the DatabaseSessionPort interface.
        """
        await session.rollback()

    @asynccontextmanager
    async def transaction(self, session: AsyncSession | None = None):
        """Transaction context manager for automatic commit/rollback.

        Args:
            session: Optional AsyncSession to use, defaults to self._session

        Usage:
            async with rdbms.transaction() as session:
                # perform database operations
                session.add(obj)

        Or with external session:
            async with rdbms.transaction(external_session) as session:
                # perform database operations
                session.add(obj)

        Automatically commits on success, rolls back on exception.
        """
        target_session = session or self._session
        try:
            yield target_session
            await target_session.commit()
        except Exception:
            await target_session.rollback()
            raise

    async def health_check(self, session: AsyncSession | None = None) -> bool:
        """Check if database connection is healthy.

        Args:
            session: Optional AsyncSession to use, defaults to self._session

        Returns:
            bool: True if connection is healthy, False otherwise
        """
        target_session = session or self._session
        try:
            result = await target_session.execute(sqlalchemy.text("SELECT 1"))
            return result.scalar() == 1
        except Exception as e:
            logging.warning(f"Database health check failed: {e}")
            return False

    async def execute_in_tx(self, func, *args, session: AsyncSession | None = None, **kwargs):
        """Execute a function within a transaction context.

        Args:
            func: Async function to execute within transaction
            *args: Positional arguments for the function
            session: Optional AsyncSession to use for the transaction
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function execution

        Example:
            result = await rdbms.execute_in_tx(
                lambda session: session.get(Model, id)
            )
        """
        async with self.transaction(session) as tx_session:
            return await func(tx_session, *args, **kwargs)

    @classmethod
    def get_primary_key_names(cls, model_class: type[TSQLModel]) -> list[str]:
        """
        Get the primary key names of a SQLModel class.
        Args:
            model_class (type[TSQLModel]): The SQLModel class to inspect.
        Returns:
            list[str]: A list of primary key names.
        """
        primary_key_names = [col.name for col in model_class.__table__.primary_key.columns.values()]  # type: ignore
        return primary_key_names

    @staticmethod
    def now_ms() -> int:
        """当前 UTC 毫秒时间戳。

        持久层 ``created_at`` / ``updated_at`` / ``run_at`` 等时间字段统一使用毫秒精度，
        此 helper 消除业务代码中反复出现的 ``int(datetime.now(UTC).timestamp() * 1000)``。
        """
        from datetime import UTC, datetime

        return int(datetime.now(UTC).timestamp() * 1000)

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_fixed(2),
        retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError),
    )
    async def insert(self, obj: SQLModel, session: AsyncSession | None = None, commit: bool = True):
        """Insert a single object into the database.

        Args:
            obj: SQLModel object to insert
            session: Optional AsyncSession to use, defaults to self._session
            commit: Whether to auto-commit (default True, set to False in transactions)

        Returns:
            The inserted object with refreshed data

        Examples:
            # Default: auto-commit
            await rdbms.insert(obj)

            # In transaction: no auto-commit
            async with rdbms.transaction() as session:
                await rdbms.insert(obj, session=session, commit=False)
        """
        target_session = session or self._session
        target_session.add(obj)

        if commit:
            await target_session.commit()

        await target_session.refresh(obj)
        return obj

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_fixed(2),
        retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError),
    )
    async def batch_insert(self, objs: list[SQLModel], session: AsyncSession | None = None, commit: bool = True):
        """Insert multiple objects into the database.

        Args:
            objs: List of SQLModel objects to insert
            session: Optional AsyncSession to use, defaults to self._session
            commit: Whether to auto-commit (default True, set to False in transactions)

        Returns:
            None

        Examples:
            # Default: auto-commit
            await rdbms.batch_insert([obj1, obj2])

            # In transaction: no auto-commit
            async with rdbms.transaction() as session:
                await rdbms.batch_insert([obj1, obj2], session=session, commit=False)
        """
        target_session = session or self._session
        target_session.add_all(objs)

        if commit:
            await target_session.commit()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_fixed(2),
        retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError),
    )
    async def get(self, model_cls: type[TSQLModel], pk: str, session: AsyncSession | None = None) -> TSQLModel | None:
        """Get an object by primary key.

        Args:
            model_cls: SQLModel class to query
            pk: Primary key value
            session: Optional AsyncSession to use, defaults to self._session

        Returns:
            The object if found, None otherwise
        """
        target_session = session or self._session
        return await target_session.get(model_cls, pk)

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_fixed(2),
        retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError),
    )
    async def get_by_filter(
        self,
        model_cls: type[TSQLModel],
        *where,
        order_by=None,
        limit=None,
        offset=None,
        for_update: bool = False,
        skip_locked: bool = False,
        session: AsyncSession | None = None,
    ) -> list[TSQLModel]:
        """Get objects by filter conditions.

        Args:
            model_cls: SQLModel class to query
            *where: WHERE conditions
            order_by: Optional 排序键（如 ``Model.created_at``），原实现缺失，现补齐
            limit: Optional limit for results
            offset: Optional offset for results
            for_update: 是否加 ``FOR UPDATE`` 行锁（并发 claim/lease 场景）
            skip_locked: 配合 for_update，跳过已被锁定的行（``SKIP LOCKED``），避免阻塞
            session: Optional AsyncSession to use, defaults to self._session

        Returns:
            List of objects matching the filter
        """
        target_session = session or self._session
        statement = select(model_cls).where(*where)
        if order_by is not None:
            statement = statement.order_by(order_by)
        if limit:
            statement = statement.limit(limit)
        if offset:
            statement = statement.offset(offset)
        if for_update:
            statement = statement.with_for_update(skip_locked=skip_locked)
        result = await target_session.execute(statement)
        return list(result.scalars().all())

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_fixed(2),
        retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError),
    )
    async def get_one(
        self,
        model_cls: type[TSQLModel],
        *where,
        order_by=None,
        for_update: bool = False,
        skip_locked: bool = False,
        session: AsyncSession | None = None,
    ) -> TSQLModel | None:
        """查询单条记录（取首条匹配），常用于 claim/lease 场景。

        是 ``get_by_filter(limit=1)`` 的便捷封装，返回单实体或 None。
        支持 ``for_update``/``skip_locked`` 以实现并发安全的「领取下一条」语义。
        """
        rows = await self.get_by_filter(
            model_cls,
            *where,
            order_by=order_by,
            limit=1,
            for_update=for_update,
            skip_locked=skip_locked,
            session=session,
        )
        return rows[0] if rows else None

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_fixed(2),
        retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError),
    )
    async def upsert(self, obj: SQLModel, sets: list[str], session: AsyncSession | None = None, commit: bool = True):
        """Insert or update an object (UPSERT operation).

        Args:
            obj: SQLModel object to upsert
            sets: List of fields to update on duplicate key
            session: Optional AsyncSession to use, defaults to self._session
            commit: Whether to auto-commit (default True, set to False in transactions)

        Returns:
            The upserted object with refreshed data

        Examples:
            # Default: auto-commit
            await rdbms.upsert(obj, ["field1", "field2"])

            # In transaction: no auto-commit
            async with rdbms.transaction() as session:
                await rdbms.upsert(obj, ["field1"], session=session, commit=False)
        """
        target_session = session or self._session
        stm = insert(obj.__class__).on_duplicate_key_update(obj.model_dump())
        await target_session.execute(stm)

        if commit:
            await target_session.commit()

        await target_session.refresh(obj)
        return obj

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_fixed(2),
        retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError),
    )
    async def list(
        self, model_cls: type[TSQLModel], page, limit, *where, session: AsyncSession | None = None
    ) -> tuple[list[TSQLModel], int]:
        """List objects with pagination.

        Args:
            model_cls: SQLModel class to query
            page: Page number (1-indexed)
            limit: Number of items per page
            *where: WHERE conditions
            session: Optional AsyncSession to use, defaults to self._session

        Returns:
            Tuple of (list of objects, total count)
        """
        target_session = session or self._session
        primary_key_names = self.get_primary_key_names(model_cls)
        primary_key_col = getattr(model_cls, primary_key_names[0])
        total_result = await target_session.execute(select(primary_key_col).where(*where))
        total = len(total_result.scalars().all())
        statement = select(model_cls).where(*where).limit(limit).offset((page - 1) * limit)
        result = await target_session.execute(statement)
        return list(result.scalars().all()), total

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_fixed(2),
        retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError),
    )
    async def update(
        self,
        model_cls: type[TSQLModel],
        updated: dict,
        *where,
        session: AsyncSession | None = None,
        commit: bool = True,
    ) -> CursorResult:
        """Update objects matching conditions.

        Args:
            model_cls: SQLModel class to update
            updated: Dictionary of field values to update
            *where: WHERE conditions
            session: Optional AsyncSession to use, defaults to self._session
            commit: Whether to auto-commit (default True, set to False in transactions)

        Returns:
            CursorResult: 执行结果，调用方可读取 ``.rowcount`` 判断匹配行数
            （向后兼容：原返回 True；CursorResult 为真值，原有 ``if await update(...)`` 仍成立）

        Examples:
            # Default: auto-commit
            await rdbms.update(Model, {"field": "value"}, Model.id == id)

            # 检查是否命中
            result = await rdbms.update(Model, {"field": "value"}, Model.id == id)
            if result.rowcount == 0:
                ...

            # In transaction: no auto-commit
            async with rdbms.transaction() as session:
                await rdbms.update(Model, {"field": "value"}, Model.id == id, session=session, commit=False)
        """
        target_session = session or self._session
        statement = update(model_cls).values(**updated).where(*where)
        logging.info(f"update sql is {statement}")

        result = await target_session.execute(statement)

        if commit:
            await target_session.commit()

        return result  # type: ignore[return-value]

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_fixed(2),
        retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError),
    )
    async def exec(self, statement: Executable, session: AsyncSession | None = None) -> Result:
        """Execute a statement and return result.

        Args:
            statement: SQL statement to execute
            session: Optional AsyncSession to use, defaults to self._session

        Returns:
            Result object from the execution
        """
        target_session = session or self._session
        return await target_session.execute(statement)

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_fixed(2),
        retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError),
    )
    async def increment_atomic(
        self,
        model_cls: type[TSQLModel],
        usage_field: str,
        usage: int,
        session: AsyncSession | None = None,
        commit: bool = True,
        **where,
    ):
        """原子增加某个字段的值.

        Args:
            model_cls: 表
            usage_field: 需要增加的字段
            usage: 增加的值
            session: Optional AsyncSession to use, defaults to self._session
            commit: Whether to auto-commit (default True, set to False in transactions)
            **where: 查询条件

        Returns:
            None

        Examples:
            # Default: auto-commit
            await rdbms.increment_atomic(Model, "counter", 1, id="key")

            # In transaction: no auto-commit
            async with rdbms.transaction() as session:
                await rdbms.increment_atomic(Model, "counter", 1, session=session, commit=False, id="key")
        """
        target_session = session or self._session
        columns = [f for f in where.keys()]
        columns.append(usage_field)
        sql = sqlalchemy.text(f"""
    INSERT INTO {model_cls.__tablename__} ({",".join(columns)})
    VALUES ({",".join([f":{col}" for col in columns])})
    ON DUPLICATE KEY UPDATE {usage_field} = {usage_field} + VALUES({usage_field});
    """)
        p = where
        p[usage_field] = usage
        await target_session.execute(sql, params=p)

        if commit:
            await target_session.commit()
