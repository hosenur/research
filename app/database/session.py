from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import database_url


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    return create_async_engine(database_url(), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_database_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session
