"""Unit tests for api/sse.py — in-process SSE event queues."""

from __future__ import annotations

import uuid

import reglens.api.sse as sse_module
from reglens.api import sse


def _unique_id() -> str:
    return str(uuid.uuid4())


def test_get_unknown_run_returns_none() -> None:
    assert sse.get("nonexistent-run-id") is None


def test_register_creates_queue() -> None:
    run_id = _unique_id()
    sse.register(run_id)
    queue = sse.get(run_id)
    assert queue is not None


def test_register_replaces_existing_queue() -> None:
    run_id = _unique_id()
    sse.register(run_id)
    q1 = sse.get(run_id)
    sse.register(run_id)
    q2 = sse.get(run_id)
    assert q2 is not q1


async def test_push_puts_event_on_queue() -> None:
    run_id = _unique_id()
    sse.register(run_id)
    event = {"node": "ingest", "status": "running"}
    await sse.push(run_id, event)
    queue = sse.get(run_id)
    assert queue is not None
    assert not queue.empty()
    received = queue.get_nowait()
    assert received == event


async def test_push_multiple_events_preserves_order() -> None:
    run_id = _unique_id()
    sse.register(run_id)
    events = [{"node": f"node_{i}", "status": "running"} for i in range(5)]
    for event in events:
        await sse.push(run_id, event)
    queue = sse.get(run_id)
    assert queue is not None
    for expected in events:
        assert queue.get_nowait() == expected


async def test_push_unknown_run_id_is_silent() -> None:
    # Should not raise even if run_id has no queue
    await sse.push("nonexistent-run-id-xyz", {"node": "test", "status": "running"})


def test_queues_are_independent() -> None:
    id1 = _unique_id()
    id2 = _unique_id()
    sse.register(id1)
    sse.register(id2)
    q1 = sse.get(id1)
    q2 = sse.get(id2)
    assert q1 is not q2
    assert sse_module._queues[id1] is not sse_module._queues[id2]
