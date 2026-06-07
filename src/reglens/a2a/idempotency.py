"""In-process idempotency store for A2A handlers.

Risk-scoring and ingestion calls are expensive (token cost, latency). When
the supervisor retries a transient A2A failure via tenacity, the server may
have already produced a successful result that just didn't reach the client.
Storing results keyed by ``(method, idempotency_key)`` lets the server short-
circuit the second attempt without re-invoking the LLM.

This is a single-process cache. Per-run retries finish within seconds and
agents are single-replica per environment, so an in-memory dict with TTL is
sufficient — moving to Redis is straightforward when the agents scale out.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

DEFAULT_TTL_SECONDS = 600  # 10 minutes — well beyond tenacity's retry window


class IdempotencyStore:
    """Async-safe TTL cache keyed by (method, idempotency_key)."""

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[tuple[str, str], tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, method: str, key: str) -> tuple[bool, Any]:
        """Return (hit, value). value is None on miss."""
        async with self._lock:
            self._evict_expired()
            entry = self._entries.get((method, key))
            if entry is None:
                return False, None
            return True, entry[0]

    async def set(self, method: str, key: str, value: Any) -> None:
        async with self._lock:
            self._entries[(method, key)] = (value, time.monotonic() + self._ttl)

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._entries.items() if exp <= now]
        for k in expired:
            del self._entries[k]
