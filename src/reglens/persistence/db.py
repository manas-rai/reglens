"""SQLAlchemy async engine and session factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from reglens.config import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> object:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            echo=settings.environment == "development",
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        from sqlalchemy.ext.asyncio import create_async_engine

        settings = get_settings()
        engine = create_async_engine(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
        )
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session
