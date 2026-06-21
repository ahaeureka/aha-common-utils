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
from typing import TYPE_CHECKING, TypeVar

import sqlalchemy
import sqlalchemy.exc
import tenacity
from pydantic import BaseModel
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.engine.result import Result
from sqlalchemy.sql import Executable
from sqlmodel import SQLModel, select, update
from tenacity import retry, stop_after_attempt, wait_fixed

logging.basicConfig()
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

TSQLModel = TypeVar('TSQLModel', bound='SQLModel')


class JSONSerializer:
    def serializer(self, value):
        if isinstance(value, BaseModel) or isinstance(value, SQLModel):
            return json.dumps(value.model_dump(), ensure_ascii=False)
        if isinstance(value, list):
            return json.dumps([v.model_dump() if isinstance(v, BaseModel) or
                               isinstance(v, SQLModel) else v for v in value],
                              ensure_ascii=False)
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
    async def transaction(self):
        """Transaction context manager for automatic commit/rollback.

        Usage:
            async with rdbms.transaction() as session:
                # perform database operations
                session.add(obj)

        Automatically commits on success, rolls back on exception.
        """
        session = self._session
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    async def health_check(self) -> bool:
        """Check if database connection is healthy.

        Returns:
            bool: True if connection is healthy, False otherwise.
        """
        try:
            result = await self._session.execute(sqlalchemy.text("SELECT 1"))
            return result.scalar() == 1
        except Exception as e:
            logging.warning(f"Database health check failed: {e}")
            return False

    async def execute_in_tx(self, func, *args, **kwargs):
        """Execute a function within a transaction context.

        Args:
            func: Async function to execute within transaction
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function execution

        Example:
            result = await rdbms.execute_in_tx(
                lambda session: session.get(Model, id)
            )
        """
        async with self.transaction() as session:
            return await func(session, *args, **kwargs)

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

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(2),
           retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError))
    async def insert(self, obj: SQLModel):
        self._session.add(obj)
        await self._session.commit()
        await self._session.refresh(obj)
        return obj

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(2),
           retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError))
    async def batch_insert(self, objs: list[SQLModel]):
        self._session.add_all(objs)
        await self._session.commit()

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(2),
           retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError))
    async def get(self, model_cls: type[TSQLModel], pk: str) -> TSQLModel | None:
        return await self._session.get(model_cls, pk)

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(2),
           retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError))
    async def get_by_filter(self, model_cls: type[TSQLModel], *where, limit=None, offset=None):
        statement = select(model_cls).where(*where)
        if limit:
            statement = statement.limit(limit)
        if offset:
            statement = statement.offset(offset)
        result = await self._session.execute(statement)
        return result.scalars().all()

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(2),
           retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError))
    async def upsert(self, obj: SQLModel, sets: list[str]):
        stm = insert(obj.__class__).on_duplicate_key_update(
            obj.model_dump())
        await self._session.execute(stm)
        await self._session.commit()
        await self._session.refresh(obj)
        return obj

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(2),
           retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError))
    async def list(self, model_cls: type[TSQLModel], page, limit, *where) -> tuple[list[TSQLModel], int]:
        primary_key_names = self.get_primary_key_names(model_cls)
        primary_key_col = getattr(model_cls, primary_key_names[0])
        total_result = await self._session.execute(select(primary_key_col).where(*where))
        total = len(total_result.scalars().all())
        statement = select(model_cls).where(
            *where).limit(limit).offset((page - 1) * limit)
        result = await self._session.execute(statement)
        return list(result.scalars().all()), total

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(2),
           retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError))
    async def update(self, model_cls: type[TSQLModel], updated: dict, *where):
        statement = update(model_cls).values(**updated).where(*where)
        logging.info(f"update sql is {statement}")

        await self._session.execute(statement)
        await self._session.commit()

        return True

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(2),
           retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError))
    async def exec(self, statement: Executable) -> Result:
        """
        Execute a statement and return a scalar result.
        """
        return await self._session.execute(statement)

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(2),
           retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError))
    async def increment_atomic(self, model_cls: type[TSQLModel], usage_field: str, usage: int, **where):
        """
        原子增加某个字段的值
        Args:
            model_cls: 表
            usage_field: 需要增加的字段
            usage: 增加的值
            where: 查询条件
        Returns
        """
        columns = [f for f in where.keys()]
        columns.append(usage_field)
        sql = sqlalchemy.text(f"""
    INSERT INTO {model_cls.__tablename__} ({",".join(columns)})
    VALUES ({",".join([f":{col}" for col in columns])})
    ON DUPLICATE KEY UPDATE {usage_field} = {usage_field} + VALUES({usage_field});
    """)
        p = where
        p[usage_field] = usage
        await self._session.execute(sql, params=p)
        await self._session.commit()
