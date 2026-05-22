"""Unit tests for api/routers/runs.py — all 5 endpoints."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI

from reglens.api.deps import require_api_key
from reglens.api.routers import runs as runs_router
from reglens.api.routers.runs import router
from reglens.schemas.report import ComplianceReport

# ---------------------------------------------------------------------------
# App fixture with auth override and API key header helper

_API_KEY = "test-api-key"
_AUTH_HEADERS = {"x-api-key": _API_KEY}


@pytest.fixture
def test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_api_key] = lambda: None  # skip auth
    return app


@pytest.fixture
def transport(test_app: FastAPI) -> httpx.ASGITransport:
    return httpx.ASGITransport(app=test_app)  # type: ignore[arg-type]


def _make_run_mock(
    run_id: str = "run-123",
    status: str = "awaiting_approval",
    domain: str = "banking",
) -> MagicMock:
    run = MagicMock()
    run.id = uuid.UUID(run_id) if "-" in run_id and len(run_id) == 36 else uuid.uuid4()
    run.id = run_id  # keep as string for simple assertion
    run.status = status
    run.domain = domain
    run.pdf_filename = "test.pdf"
    run.error_message = None
    run.created_at = datetime(2024, 1, 1, 0, 0, 0)
    run.updated_at = datetime(2024, 1, 1, 0, 1, 0)
    return run


def _mock_db_session_factory(run_model: Any = None):
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=run_model)
    mock_session.add = MagicMock()

    @asynccontextmanager
    async def _ctx():
        yield mock_session

    return _ctx


# ---------------------------------------------------------------------------
# POST /runs


async def test_create_run_returns_202(transport: httpx.ASGITransport) -> None:
    run = _make_run_mock()
    db_ctx = _mock_db_session_factory(run)

    with (
        patch.object(runs_router, "db_session", db_ctx),
        patch.object(runs_router, "sse") as mock_sse,
        patch.object(runs_router, "run_pipeline", new=AsyncMock()),
    ):
        mock_sse.register = MagicMock()
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/runs",
                files={"pdf": ("test.pdf", b"%PDF fake", "application/pdf")},
                data={"regulation_ref": "REG-001", "domain": "banking"},
            )

    assert resp.status_code == 202
    body = resp.json()
    assert "run_id" in body
    assert body["status"] == "pending"


async def test_create_run_registers_sse_queue(transport: httpx.ASGITransport) -> None:
    run = _make_run_mock()
    db_ctx = _mock_db_session_factory(run)

    with (
        patch.object(runs_router, "db_session", db_ctx),
        patch.object(runs_router, "sse") as mock_sse,
        patch.object(runs_router, "run_pipeline", new=AsyncMock()),
    ):
        mock_sse.register = MagicMock()
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            await client.post(
                "/runs",
                files={"pdf": ("test.pdf", b"%PDF", "application/pdf")},
            )

    mock_sse.register.assert_called_once()


# ---------------------------------------------------------------------------
# GET /runs/{run_id}


async def test_get_run_found(transport: httpx.ASGITransport) -> None:
    run = _make_run_mock(status="running")
    db_ctx = _mock_db_session_factory(run)
    run_id = str(uuid.uuid4())

    with patch.object(runs_router, "db_session", db_ctx):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get(f"/runs/{run_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "running"
    assert body["domain"] == "banking"


async def test_get_run_not_found(transport: httpx.ASGITransport) -> None:
    db_ctx = _mock_db_session_factory(None)  # session.get returns None
    run_id = str(uuid.uuid4())

    with patch.object(runs_router, "db_session", db_ctx):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get(f"/runs/{run_id}")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/events


async def test_run_events_no_queue_returns_404(transport: httpx.ASGITransport) -> None:
    with patch.object(runs_router, "sse") as mock_sse:
        mock_sse.get = MagicMock(return_value=None)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get(f"/runs/{uuid.uuid4()}/events")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /runs/{run_id}/approve


async def test_approve_run_awaiting_approval(transport: httpx.ASGITransport) -> None:
    run = _make_run_mock(status="awaiting_approval")
    db_ctx = _mock_db_session_factory(run)
    run_id = str(uuid.uuid4())

    with (
        patch.object(runs_router, "db_session", db_ctx),
        patch.object(runs_router, "resume_pipeline", new=AsyncMock()),
    ):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/runs/{run_id}/approve",
                json={"approved": True, "edits": []},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "resuming"


async def test_approve_run_rejected(transport: httpx.ASGITransport) -> None:
    run = _make_run_mock(status="awaiting_approval")
    db_ctx = _mock_db_session_factory(run)
    run_id = str(uuid.uuid4())

    with (
        patch.object(runs_router, "db_session", db_ctx),
        patch.object(runs_router, "resume_pipeline", new=AsyncMock()),
    ):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/runs/{run_id}/approve",
                json={"approved": False, "edits": []},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"


async def test_approve_run_not_found(transport: httpx.ASGITransport) -> None:
    db_ctx = _mock_db_session_factory(None)
    run_id = str(uuid.uuid4())

    with patch.object(runs_router, "db_session", db_ctx):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/runs/{run_id}/approve",
                json={"approved": True, "edits": []},
            )

    assert resp.status_code == 404


async def test_approve_run_wrong_status_returns_409(
    transport: httpx.ASGITransport,
) -> None:
    run = _make_run_mock(status="running")  # not awaiting_approval
    db_ctx = _mock_db_session_factory(run)
    run_id = str(uuid.uuid4())

    with patch.object(runs_router, "db_session", db_ctx):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/runs/{run_id}/approve",
                json={"approved": True, "edits": []},
            )

    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/report


async def test_get_report_success(transport: httpx.ASGITransport) -> None:
    run = _make_run_mock(status="completed")
    db_ctx = _mock_db_session_factory(run)
    run_id = str(uuid.uuid4())

    report_data = {
        "run_id": run_id,
        "regulation_ref": "REG",
        "domain": "banking",
        "summary": {},
    }

    mock_state = MagicMock()
    mock_state.values = {"final_report": report_data}

    mock_graph = AsyncMock()
    mock_graph.aget_state = AsyncMock(return_value=mock_state)

    mock_cp = MagicMock()

    @asynccontextmanager
    async def mock_cp_ctx():
        yield mock_cp

    with (
        patch.object(runs_router, "db_session", db_ctx),
        patch.object(runs_router, "get_checkpointer", mock_cp_ctx),
        patch.object(runs_router, "build_supervisor_graph", return_value=mock_graph),
    ):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get(f"/runs/{run_id}/report")

    assert resp.status_code == 200
    assert resp.json()["run_id"] == run_id


async def test_get_report_compliance_report_object(
    transport: httpx.ASGITransport,
) -> None:
    """ComplianceReport objects are serialized via model_dump."""
    run = _make_run_mock(status="completed")
    db_ctx = _mock_db_session_factory(run)
    run_id = str(uuid.uuid4())

    report = ComplianceReport.build(run_id, "REG", "banking", [])

    mock_state = MagicMock()
    mock_state.values = {"final_report": report}

    mock_graph = AsyncMock()
    mock_graph.aget_state = AsyncMock(return_value=mock_state)

    mock_cp = MagicMock()

    @asynccontextmanager
    async def mock_cp_ctx():
        yield mock_cp

    with (
        patch.object(runs_router, "db_session", db_ctx),
        patch.object(runs_router, "get_checkpointer", mock_cp_ctx),
        patch.object(runs_router, "build_supervisor_graph", return_value=mock_graph),
    ):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get(f"/runs/{run_id}/report")

    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == run_id


async def test_get_report_run_not_found(transport: httpx.ASGITransport) -> None:
    db_ctx = _mock_db_session_factory(None)
    run_id = str(uuid.uuid4())

    with patch.object(runs_router, "db_session", db_ctx):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get(f"/runs/{run_id}/report")

    assert resp.status_code == 404


async def test_get_report_not_completed_returns_409(
    transport: httpx.ASGITransport,
) -> None:
    run = _make_run_mock(status="running")
    db_ctx = _mock_db_session_factory(run)
    run_id = str(uuid.uuid4())

    with patch.object(runs_router, "db_session", db_ctx):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get(f"/runs/{run_id}/report")

    assert resp.status_code == 409


async def test_get_report_missing_in_state_returns_404(
    transport: httpx.ASGITransport,
) -> None:
    run = _make_run_mock(status="completed")
    db_ctx = _mock_db_session_factory(run)
    run_id = str(uuid.uuid4())

    mock_state = MagicMock()
    mock_state.values = {}  # no final_report

    mock_graph = AsyncMock()
    mock_graph.aget_state = AsyncMock(return_value=mock_state)

    mock_cp = MagicMock()

    @asynccontextmanager
    async def mock_cp_ctx():
        yield mock_cp

    with (
        patch.object(runs_router, "db_session", db_ctx),
        patch.object(runs_router, "get_checkpointer", mock_cp_ctx),
        patch.object(runs_router, "build_supervisor_graph", return_value=mock_graph),
    ):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get(f"/runs/{run_id}/report")

    assert resp.status_code == 404
