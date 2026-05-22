"""In-process SSE event queues — one asyncio.Queue per active run."""

from __future__ import annotations

import asyncio
from typing import Any

_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}


def register(run_id: str) -> None:
    _queues[run_id] = asyncio.Queue()


def get(run_id: str) -> asyncio.Queue[dict[str, Any]] | None:
    return _queues.get(run_id)


async def push(run_id: str, event: dict[str, Any]) -> None:
    queue = _queues.get(run_id)
    if queue:
        await queue.put(event)
