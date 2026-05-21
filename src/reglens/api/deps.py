"""FastAPI dependency injection — DB sessions, settings, auth."""

from __future__ import annotations

from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from reglens.config import Settings, get_settings
from reglens.persistence.db import async_session_factory


async def get_db() -> AsyncSession:  # type: ignore[return]
    async with async_session_factory() as session:
        yield session


def get_api_settings() -> Settings:
    return get_settings()


async def require_api_key(
    x_api_key: str = Header(..., alias="x-api-key"),
) -> None:
    settings = get_settings()
    if x_api_key != settings.api_key.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
