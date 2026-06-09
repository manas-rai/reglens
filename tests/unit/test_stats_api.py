"""Unit tests for api/routers/stats.py."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI

from reglens.api.deps import require_api_key
from reglens.api.routers import stats as stats_router
from reglens.api.routers.stats import router


@pytest.fixture
def test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_api_key] = lambda: None
    return app


@pytest.fixture
def transport(test_app: FastAPI) -> httpx.ASGITransport:
    return httpx.ASGITransport(app=test_app)  # type: ignore[arg-type]


async def test_get_stats_aggregates(transport: httpx.ASGITransport) -> None:
    """Stats endpoint sums execute results in the order issued: count, group-by, sum."""
    total_result = MagicMock()
    total_result.scalar_one.return_value = 12

    status_result = MagicMock()
    status_result.all.return_value = [("completed", 8), ("running", 3), ("rejected", 1)]

    cost_result = MagicMock()
    cost_result.scalar_one.return_value = 0.4567

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=[total_result, status_result, cost_result]
    )

    @asynccontextmanager
    async def db_ctx():
        yield mock_session

    with patch.object(stats_router, "db_session", db_ctx):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/stats")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_runs"] == 12
    assert body["by_status"] == {"completed": 8, "running": 3, "rejected": 1}
    assert abs(body["total_cost_usd"] - 0.4567) < 1e-9


async def test_get_stats_empty_db(transport: httpx.ASGITransport) -> None:
    total_result = MagicMock()
    total_result.scalar_one.return_value = 0
    status_result = MagicMock()
    status_result.all.return_value = []
    cost_result = MagicMock()
    cost_result.scalar_one.return_value = 0

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=[total_result, status_result, cost_result]
    )

    @asynccontextmanager
    async def db_ctx():
        yield mock_session

    with patch.object(stats_router, "db_session", db_ctx):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/stats")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_runs"] == 0
    assert body["by_status"] == {}
    assert body["total_cost_usd"] == 0.0
