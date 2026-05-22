"""Unit tests for supervisor/pipeline.py — run_pipeline, resume_pipeline, update_run_status."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from reglens.supervisor.pipeline import resume_pipeline, run_pipeline, update_run_status


def _mock_db_session():
    mock_session = AsyncMock()

    @asynccontextmanager
    async def _session_ctx():
        yield mock_session

    return _session_ctx, mock_session


def _mock_checkpointer_ctx():
    mock_cp = MagicMock()

    @asynccontextmanager
    async def _ctx():
        yield mock_cp

    return _ctx, mock_cp


def _mock_graph(events: list, *, interrupted: bool = True) -> AsyncMock:
    """Build a mock graph whose astream yields events and aget_state reflects interrupt status."""
    mock_graph = AsyncMock()
    mock_graph.astream = MagicMock(return_value=_async_iter(events))
    final_state = MagicMock()
    # state.next is non-empty when the graph is paused at interrupt(), empty when it reached END
    final_state.next = ("generate_report",) if interrupted else ()
    mock_graph.aget_state = AsyncMock(return_value=final_state)
    return mock_graph


# ---------------------------------------------------------------------------
# update_run_status


async def test_update_run_status_no_error() -> None:
    ctx, session = _mock_db_session()
    with patch("reglens.supervisor.pipeline.db_session", ctx):
        await update_run_status("run-123", "running")
    session.execute.assert_called_once()
    call_args = session.execute.call_args
    params = call_args[0][1]
    assert params["status"] == "running"
    assert params["id"] == "run-123"
    assert "error" not in params


async def test_update_run_status_with_error() -> None:
    ctx, session = _mock_db_session()
    with patch("reglens.supervisor.pipeline.db_session", ctx):
        await update_run_status("run-456", "error", "Something exploded")
    params = session.execute.call_args[0][1]
    assert params["status"] == "error"
    assert params["error"] == "Something exploded"


# ---------------------------------------------------------------------------
# run_pipeline


async def test_run_pipeline_success() -> None:
    ctx, _ = _mock_db_session()
    cp_ctx, _ = _mock_checkpointer_ctx()

    with (
        patch("reglens.supervisor.pipeline.db_session", ctx),
        patch("reglens.supervisor.pipeline.get_checkpointer", cp_ctx),
        patch(
            "reglens.supervisor.pipeline.build_supervisor_graph",
            return_value=_mock_graph([{"ingest": {}}, {"generate_report": {}}]),
        ),
        patch("reglens.supervisor.pipeline.sse.push", new=AsyncMock()),
    ):
        await run_pipeline("run-001", b"pdf", "REG-2024", "banking")


async def test_run_pipeline_sse_events_pushed() -> None:
    ctx, _ = _mock_db_session()
    cp_ctx, _ = _mock_checkpointer_ctx()

    push_mock = AsyncMock()
    with (
        patch("reglens.supervisor.pipeline.db_session", ctx),
        patch("reglens.supervisor.pipeline.get_checkpointer", cp_ctx),
        patch(
            "reglens.supervisor.pipeline.build_supervisor_graph",
            return_value=_mock_graph([{"ingest": {}}, {"generate_report": {}}]),
        ),
        patch("reglens.supervisor.pipeline.sse.push", push_mock),
    ):
        await run_pipeline("run-002", b"pdf", "REG", "banking")

    # start + ingest + generate_report + awaiting_approval
    assert push_mock.call_count >= 3


async def test_run_pipeline_updates_status_to_awaiting_approval() -> None:
    ctx, session = _mock_db_session()
    cp_ctx, _ = _mock_checkpointer_ctx()

    with (
        patch("reglens.supervisor.pipeline.db_session", ctx),
        patch("reglens.supervisor.pipeline.get_checkpointer", cp_ctx),
        patch(
            "reglens.supervisor.pipeline.build_supervisor_graph",
            return_value=_mock_graph([]),
        ),
        patch("reglens.supervisor.pipeline.sse.push", new=AsyncMock()),
    ):
        await run_pipeline("run-003", b"pdf", "REG", "banking")

    statuses = [c[0][1]["status"] for c in session.execute.call_args_list]
    assert "running" in statuses
    assert "awaiting_approval" in statuses


async def test_run_pipeline_handles_exception() -> None:
    ctx, _ = _mock_db_session()
    cp_ctx, _ = _mock_checkpointer_ctx()

    mock_graph = AsyncMock()
    mock_graph.astream = MagicMock(side_effect=RuntimeError("graph blew up"))

    push_mock = AsyncMock()
    with (
        patch("reglens.supervisor.pipeline.db_session", ctx),
        patch("reglens.supervisor.pipeline.get_checkpointer", cp_ctx),
        patch(
            "reglens.supervisor.pipeline.build_supervisor_graph",
            return_value=mock_graph,
        ),
        patch("reglens.supervisor.pipeline.sse.push", push_mock),
    ):
        await run_pipeline("run-004", b"pdf", "REG", "banking")

    error_calls = [
        c for c in push_mock.call_args_list if c[0][1].get("status") == "error"
    ]
    assert len(error_calls) == 1


async def test_run_pipeline_empty_obligations_completes_without_hitl() -> None:
    """When graph reaches END naturally (empty report), status is completed not awaiting_approval."""
    ctx, session = _mock_db_session()
    cp_ctx, _ = _mock_checkpointer_ctx()

    push_mock = AsyncMock()
    with (
        patch("reglens.supervisor.pipeline.db_session", ctx),
        patch("reglens.supervisor.pipeline.get_checkpointer", cp_ctx),
        patch(
            "reglens.supervisor.pipeline.build_supervisor_graph",
            return_value=_mock_graph(
                [{"ingest": {}}, {"empty_report": {}}], interrupted=False
            ),
        ),
        patch("reglens.supervisor.pipeline.sse.push", push_mock),
    ):
        await run_pipeline("run-empty", b"pdf", "REG", "banking")

    statuses = [c[0][1]["status"] for c in session.execute.call_args_list]
    assert "completed" in statuses
    assert "awaiting_approval" not in statuses

    terminal_events = [c[0][1].get("status") for c in push_mock.call_args_list]
    assert "completed" in terminal_events
    assert "awaiting_approval" not in terminal_events


# ---------------------------------------------------------------------------
# resume_pipeline


async def test_resume_pipeline_approved() -> None:
    ctx, _ = _mock_db_session()
    cp_ctx, _ = _mock_checkpointer_ctx()

    mock_graph = AsyncMock()
    mock_graph.astream = MagicMock(return_value=_async_iter([{"done": {}}]))

    push_mock = AsyncMock()
    with (
        patch("reglens.supervisor.pipeline.db_session", ctx),
        patch("reglens.supervisor.pipeline.get_checkpointer", cp_ctx),
        patch(
            "reglens.supervisor.pipeline.build_supervisor_graph",
            return_value=mock_graph,
        ),
        patch("reglens.supervisor.pipeline.sse.push", push_mock),
    ):
        await resume_pipeline("run-005", approved=True, edits=[])

    terminal_calls = [
        c for c in push_mock.call_args_list if c[0][1].get("status") == "completed"
    ]
    assert len(terminal_calls) == 1


async def test_resume_pipeline_rejected() -> None:
    ctx, _ = _mock_db_session()
    cp_ctx, _ = _mock_checkpointer_ctx()

    mock_graph = AsyncMock()
    mock_graph.astream = MagicMock(return_value=_async_iter([]))

    push_mock = AsyncMock()
    with (
        patch("reglens.supervisor.pipeline.db_session", ctx),
        patch("reglens.supervisor.pipeline.get_checkpointer", cp_ctx),
        patch(
            "reglens.supervisor.pipeline.build_supervisor_graph",
            return_value=mock_graph,
        ),
        patch("reglens.supervisor.pipeline.sse.push", push_mock),
    ):
        await resume_pipeline("run-006", approved=False, edits=[])

    terminal_calls = [
        c for c in push_mock.call_args_list if c[0][1].get("status") == "rejected"
    ]
    assert len(terminal_calls) == 1


async def test_resume_pipeline_handles_exception() -> None:
    ctx, _ = _mock_db_session()
    cp_ctx, _ = _mock_checkpointer_ctx()

    mock_graph = AsyncMock()
    mock_graph.astream = MagicMock(side_effect=RuntimeError("crash"))

    push_mock = AsyncMock()
    with (
        patch("reglens.supervisor.pipeline.db_session", ctx),
        patch("reglens.supervisor.pipeline.get_checkpointer", cp_ctx),
        patch(
            "reglens.supervisor.pipeline.build_supervisor_graph",
            return_value=mock_graph,
        ),
        patch("reglens.supervisor.pipeline.sse.push", push_mock),
    ):
        await resume_pipeline("run-007", approved=True, edits=[])

    error_calls = [
        c for c in push_mock.call_args_list if c[0][1].get("status") == "error"
    ]
    assert len(error_calls) == 1


def _async_iter(items):
    """Return an async iterable from a list."""

    async def _gen():
        for item in items:
            yield item

    return _gen()
