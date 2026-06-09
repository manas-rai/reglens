"""Unit tests for api/routers/policies.py."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI

from reglens.api.deps import require_api_key
from reglens.api.routers import policies as policies_router
from reglens.api.routers.policies import router


@pytest.fixture
def test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_api_key] = lambda: None
    return app


@pytest.fixture
def transport(test_app: FastAPI) -> httpx.ASGITransport:
    return httpx.ASGITransport(app=test_app)  # type: ignore[arg-type]


def _row(policy_id: str, **overrides: Any) -> dict[str, Any]:
    return {
        "id": policy_id,
        "domain": overrides.get("domain", "banking"),
        "section": overrides.get("section", "KYC §3"),
        "title": overrides.get("title", "Customer ID Programme"),
        "text": overrides.get("text", "Banks shall verify identity."),
        "owner": overrides.get("owner", "compliance"),
        "tags": overrides.get("tags", "kyc"),
        "created_at": overrides.get("created_at", datetime(2024, 1, 1)),
    }


def _mock_session_returning(rows: list[dict[str, Any]] | dict[str, Any] | None):
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mappings = MagicMock()
    if isinstance(rows, list):
        mappings.all = MagicMock(return_value=rows)
        mappings.first = MagicMock(return_value=rows[0] if rows else None)
    else:
        mappings.first = MagicMock(return_value=rows)
        mappings.all = MagicMock(return_value=[rows] if rows else [])
    mock_result.mappings = MagicMock(return_value=mappings)
    mock_session.execute = AsyncMock(return_value=mock_result)

    @asynccontextmanager
    async def _ctx():
        yield mock_session

    return _ctx, mock_session


async def test_list_policies_returns_items(transport: httpx.ASGITransport) -> None:
    rows = [_row("CTL-KYC-001"), _row("CTL-AML-001", section="AML §5")]
    db_ctx, _ = _mock_session_returning(rows)

    with patch.object(policies_router, "db_session", db_ctx):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/policies?limit=10&offset=0")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["items"][0]["id"] == "CTL-KYC-001"
    assert body["limit"] == 10


async def test_list_policies_passes_filters(transport: httpx.ASGITransport) -> None:
    db_ctx, mock_session = _mock_session_returning([])
    with patch.object(policies_router, "db_session", db_ctx):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/policies?domain=banking&q=kyc")
    assert resp.status_code == 200
    params = mock_session.execute.call_args[0][1]
    assert params["domain"] == "banking"
    assert params["q"] == "%kyc%"


async def test_get_policy_404(transport: httpx.ASGITransport) -> None:
    db_ctx, _ = _mock_session_returning(None)
    with patch.object(policies_router, "db_session", db_ctx):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/policies/UNKNOWN")
    assert resp.status_code == 404


async def test_get_policy_returns_detail(transport: httpx.ASGITransport) -> None:
    db_ctx, _ = _mock_session_returning(_row("CTL-KYC-001"))
    with patch.object(policies_router, "db_session", db_ctx):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/policies/CTL-KYC-001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "CTL-KYC-001"
    assert body["title"] == "Customer ID Programme"
