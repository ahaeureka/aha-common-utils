#!/usr/bin/env python
'''
@File    :   db.py
@Time    :   2024/07/04 17:22:52
@Desc    :
'''


import json
import logging
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

# logging.getLogger('sqlalchemy.engine.Engine').setLevel(logging.ERROR)
# logging.getLogger('sqlalchemy').setLevel(logging.ERROR)
# logging.getLogger("sqlalchemy.engine").setLevel(logging.ERROR)
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
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
    @classmethod
    def get_primary_key_names(cls, model_class: type[TSQLModel]) -> list[str]:
        """
        Get the primary key names of a SQLModel class.
        Args:
            model_class (type[TSQLModel]): The SQLModel class to inspect.
        Returns:
            list[str]: A list of primary key names.
        """
        primary_key_names = [col.name for col in model_class.__table__.primary_key.columns.values()] # type: ignore
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
        # await self._session.refresh(objs)

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(2),
           retry=tenacity.retry_if_exception_type(sqlalchemy.exc.OperationalError))
    async def get(self, model_cls: type[TSQLModel], pk: str)->TSQLModel | None:
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
        # values = [where[k] for k in columns]
        columns.append(usage_field)
        # values.append(usage)
        sql = sqlalchemy.text(f"""
    INSERT INTO {model_cls.__tablename__} ({",".join(columns)})
    VALUES ({",".join([f":{col}" for col in columns])})
    ON DUPLICATE KEY UPDATE {usage_field} = {usage_field} + VALUES({usage_field});
    """)
        p = where
        p[usage_field] = usage
        await self._session.execute(sql, params=p)
        await self._session.commit()
