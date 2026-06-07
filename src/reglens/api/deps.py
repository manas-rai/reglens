"""FastAPI dependency injection — settings, auth."""

from __future__ import annotations

from fastapi import Header, HTTPException, Query, status

from reglens.config import get_settings


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    api_key_query: str | None = Query(default=None, alias="x-api-key"),
) -> None:
    """Accept the API key from either the ``x-api-key`` header or query string.

    The query-string fallback exists for SSE in the browser: ``EventSource``
    cannot set custom headers, so the demo UI passes the key as ``?x-api-key=``.
    """
    settings = get_settings()
    provided = x_api_key or api_key_query
    if provided != settings.api_key.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
