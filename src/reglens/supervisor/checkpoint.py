"""PostgresSaver checkpointer wiring for LangGraph."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from reglens.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def get_checkpointer() -> AsyncIterator[AsyncPostgresSaver]:
    """Provide an AsyncPostgresSaver for the duration of a request."""
    settings = get_settings()
    # langgraph-checkpoint-postgres expects the raw psycopg connection string
    # (without the SQLAlchemy dialect prefix)
    conn_str = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    async with AsyncPostgresSaver.from_conn_string(conn_str) as saver:
        await saver.setup()
        yield saver
