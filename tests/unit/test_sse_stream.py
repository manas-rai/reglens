"""Tests for SSE streaming endpoint and LLM lru_cache factories."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest
import sse_starlette.sse as sse_lib
from fastapi import FastAPI

from reglens.api import sse
from reglens.api.deps import require_api_key
from reglens.api.routers.runs import router


@pytest.fixture(autouse=True)
def reset_sse_exit_event():
    """Reset sse_starlette's global asyncio.Event to the current test loop."""
    original = sse_lib.AppStatus.should_exit_event
    sse_lib.AppStatus.should_exit_event = asyncio.Event()
    yield
    sse_lib.AppStatus.should_exit_event = original


# ---------------------------------------------------------------------------
# SSE streaming generator (runs.py lines 109-121)


@pytest.fixture
def stream_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_api_key] = lambda: None
    return app


async def test_sse_stream_yields_events_and_terminates(
    stream_test_app: FastAPI,
) -> None:
    """SSE generator yields events until a terminal status is seen."""
    run_id = "stream-test-run"
    sse.register(run_id)

    # Pre-load events: a progress event then a terminal "completed" event
    await sse.push(run_id, {"node": "ingest", "status": "running"})
    await sse.push(run_id, {"node": "done", "status": "completed"})

    transport = httpx.ASGITransport(app=stream_test_app)  # type: ignore[arg-type]
    chunks: list[str] = []
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        client.stream("GET", f"/runs/{run_id}/events") as response,
    ):
        assert response.status_code == 200
        async for chunk in response.aiter_text():
            chunks.append(chunk)

    full_body = "".join(chunks)
    assert "running" in full_body
    assert "completed" in full_body


async def test_sse_stream_terminates_on_error_status(stream_test_app: FastAPI) -> None:
    run_id = "stream-error-run"
    sse.register(run_id)
    await sse.push(run_id, {"node": "error", "status": "error", "detail": "boom"})

    transport = httpx.ASGITransport(app=stream_test_app)  # type: ignore[arg-type]
    chunks: list[str] = []
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        client.stream("GET", f"/runs/{run_id}/events") as response,
    ):
        assert response.status_code == 200
        async for chunk in response.aiter_text():
            chunks.append(chunk)

    assert "error" in "".join(chunks)


async def test_sse_stream_terminates_on_rejected_status(
    stream_test_app: FastAPI,
) -> None:
    run_id = "stream-rejected-run"
    sse.register(run_id)
    await sse.push(run_id, {"node": "done", "status": "rejected"})

    transport = httpx.ASGITransport(app=stream_test_app)  # type: ignore[arg-type]
    chunks: list[str] = []
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        client.stream("GET", f"/runs/{run_id}/events") as response,
    ):
        async for chunk in response.aiter_text():
            chunks.append(chunk)

    assert "rejected" in "".join(chunks)


async def test_sse_stream_terminates_on_awaiting_approval(
    stream_test_app: FastAPI,
) -> None:
    run_id = "stream-hitl-run"
    sse.register(run_id)
    await sse.push(run_id, {"node": "generate_report", "status": "awaiting_approval"})

    transport = httpx.ASGITransport(app=stream_test_app)  # type: ignore[arg-type]
    chunks: list[str] = []
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        client.stream("GET", f"/runs/{run_id}/events") as response,
    ):
        async for chunk in response.aiter_text():
            chunks.append(chunk)

    assert "awaiting_approval" in "".join(chunks)


# ---------------------------------------------------------------------------
# LLM lru_cache factories


def test_get_instructor_client_is_async_instructor() -> None:
    import instructor

    import reglens.llm.claude as claude_module

    claude_module._get_instructor_client.cache_clear()
    mock_settings = MagicMock()
    mock_settings.anthropic_api_key.get_secret_value.return_value = "test-key"

    try:
        with patch.object(claude_module, "get_settings", return_value=mock_settings):
            client = claude_module._get_instructor_client()
        assert isinstance(client, instructor.AsyncInstructor)
    finally:
        claude_module._get_instructor_client.cache_clear()


def test_get_generation_client_returns_genai_client() -> None:
    from google import genai

    import reglens.llm.gemini as gemini_module

    gemini_module._get_generation_client.cache_clear()
    mock_settings = MagicMock()
    mock_settings.gemini_api_key.get_secret_value.return_value = "test-key"

    try:
        with patch.object(gemini_module, "get_settings", return_value=mock_settings):
            client = gemini_module._get_generation_client()
        assert isinstance(client, genai.Client)
    finally:
        gemini_module._get_generation_client.cache_clear()


def test_get_embedding_client_returns_genai_client() -> None:
    from google import genai

    import reglens.llm.gemini as gemini_module

    gemini_module._get_embedding_client.cache_clear()
    mock_settings = MagicMock()
    mock_settings.gemini_api_key.get_secret_value.return_value = "test-key"

    try:
        with patch.object(gemini_module, "get_settings", return_value=mock_settings):
            client = gemini_module._get_embedding_client()
        assert isinstance(client, genai.Client)
    finally:
        gemini_module._get_embedding_client.cache_clear()
