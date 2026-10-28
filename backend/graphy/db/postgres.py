"""PostgreSQL engines. The API uses the async engine; background jobs and Alembic use the sync one.

psycopg 3 serves both from the same postgresql+psycopg:// URL.
"""

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from graphy.config import get_settings


@lru_cache
def async_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def _async_sessions() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(async_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with _async_sessions()() as session:
        yield session


@lru_cache
def sync_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@contextmanager
def sync_session() -> Iterator[Session]:
    with sessionmaker(sync_engine(), expire_on_commit=False)() as session:
        yield session
