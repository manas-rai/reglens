"""Background pipeline tasks — run and resume the compliance analysis graph."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from reglens.api import sse
from reglens.persistence.db import db_session
from reglens.supervisor.checkpoint import get_checkpointer
from reglens.supervisor.graph import build_supervisor_graph
from reglens.supervisor.state import SupervisorState

logger = logging.getLogger(__name__)


async def update_run_status(
    run_id: str, new_status: str, error: str | None = None
) -> None:
    async with db_session() as session:
        if error:
            await session.execute(
                text(
                    "UPDATE runs SET status = :status, error_message = :error,"
                    " updated_at = now() WHERE id = CAST(:id AS uuid)"
                ),
                {"status": new_status, "error": error, "id": run_id},
            )
        else:
            await session.execute(
                text(
                    "UPDATE runs SET status = :status, updated_at = now()"
                    " WHERE id = CAST(:id AS uuid)"
                ),
                {"status": new_status, "id": run_id},
            )


async def run_pipeline(
    run_id: str,
    pdf_bytes: bytes,
    regulation_ref: str,
    domain: str,
) -> None:
    try:
        await update_run_status(run_id, "running")
        await sse.push(run_id, {"node": "start", "status": "running"})
        logger.info("Pipeline started", extra={"run_id": run_id})

        initial_state: SupervisorState = {
            "run_id": run_id,
            "pdf_bytes": pdf_bytes,
            "regulation_ref": regulation_ref,
            "domain": domain,
        }

        async with get_checkpointer() as checkpointer:
            graph = build_supervisor_graph(checkpointer)
            config = {"configurable": {"thread_id": run_id}}

            async for event in graph.astream(
                initial_state, config=config, stream_mode="updates"
            ):
                node_name = next(iter(event)) if event else "unknown"
                logger.info(
                    "Node completed", extra={"run_id": run_id, "node": node_name}
                )
                await sse.push(run_id, {"node": node_name, "status": "running"})

        await update_run_status(run_id, "awaiting_approval")
        await sse.push(
            run_id, {"node": "generate_report", "status": "awaiting_approval"}
        )
        logger.info("Pipeline paused — awaiting approval", extra={"run_id": run_id})

    except Exception as exc:
        logger.exception("Pipeline failed", extra={"run_id": run_id, "error": str(exc)})
        await update_run_status(run_id, "error", str(exc))
        await sse.push(run_id, {"node": "error", "status": "error", "detail": str(exc)})


async def resume_pipeline(
    run_id: str,
    approved: bool,
    edits: list[dict[str, Any]],
) -> None:
    try:
        await update_run_status(run_id, "running")
        await sse.push(run_id, {"node": "resume", "status": "running"})
        logger.info(
            "Pipeline resuming after approval",
            extra={"run_id": run_id, "approved": approved},
        )

        from langgraph.types import Command

        async with get_checkpointer() as checkpointer:
            graph = build_supervisor_graph(checkpointer)
            config = {"configurable": {"thread_id": run_id}}

            resume_cmd = Command(resume={"approved": approved, "edits": edits})
            async for event in graph.astream(
                resume_cmd, config=config, stream_mode="updates"
            ):
                node_name = next(iter(event)) if event else "unknown"
                logger.info(
                    "Node completed", extra={"run_id": run_id, "node": node_name}
                )
                await sse.push(run_id, {"node": node_name, "status": "running"})

        final_status = "completed" if approved else "rejected"
        await sse.push(run_id, {"node": "done", "status": final_status})
        logger.info(
            "Pipeline finished", extra={"run_id": run_id, "status": final_status}
        )

    except Exception as exc:
        logger.exception(
            "Pipeline resume failed", extra={"run_id": run_id, "error": str(exc)}
        )
        await update_run_status(run_id, "error", str(exc))
        await sse.push(run_id, {"node": "error", "status": "error", "detail": str(exc)})
