"""FastAPI dependency injection — settings, auth."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from reglens.config import get_settings


async def require_api_key(
    x_api_key: str = Header(..., alias="x-api-key"),
) -> None:
    settings = get_settings()
    if x_api_key != settings.api_key.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
