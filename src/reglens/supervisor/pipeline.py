"""Background pipeline tasks — run and resume the compliance analysis graph."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy import text

from evals.metrics.run_metrics import compute_run_metrics, write_run_metrics
from reglens.api import sse
from reglens.persistence.db import db_session
from reglens.supervisor.checkpoint import get_checkpointer
from reglens.supervisor.graph import build_supervisor_graph
from reglens.supervisor.state import SupervisorState

logger = logging.getLogger(__name__)


def _build_runnable_config(
    run_id: str,
    regulation_ref: str | None = None,
    domain: str | None = None,
    *,
    operation: str,
) -> RunnableConfig:
    """Build a LangGraph RunnableConfig with LangSmith trace metadata.

    ``operation`` labels the top-level trace ("run" vs "resume") so LangSmith
    can distinguish initial executions from HITL resumes for the same thread.
    """
    # Read ENVIRONMENT directly rather than calling get_settings() so this
    # helper stays usable in tests that don't construct a full Settings object.
    environment = os.environ.get("ENVIRONMENT", "development")
    metadata: dict[str, Any] = {"run_id": run_id, "operation": operation}
    tags: list[str] = [environment, operation]
    if regulation_ref is not None:
        metadata["regulation_ref"] = regulation_ref
    if domain is not None:
        metadata["domain"] = domain
        tags.append(domain)
    return {
        "configurable": {"thread_id": run_id},
        "run_name": f"reglens.compliance_{operation}",
        "tags": tags,
        "metadata": metadata,
    }


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
    started_at = time.monotonic()
    node_sequence: list[str] = []
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
            config = _build_runnable_config(
                run_id, regulation_ref, domain, operation="run"
            )

            async for event in graph.astream(
                initial_state, config=config, stream_mode="updates"
            ):
                node_name = next(iter(event)) if event else "unknown"
                node_sequence.append(node_name)
                logger.info(
                    "Node completed", extra={"run_id": run_id, "node": node_name}
                )
                await sse.push(run_id, {"node": node_name, "status": "running"})

            # Distinguish interrupted (HITL gate) from naturally completed (empty report).
            # state.next is non-empty when the graph is paused at an interrupt().
            final_state = await graph.aget_state(config)

        await _emit_run_metrics(run_id, final_state, node_sequence, started_at)

        if final_state.next:
            await update_run_status(run_id, "awaiting_approval")
            await sse.push(
                run_id, {"node": "generate_report", "status": "awaiting_approval"}
            )
            logger.info("Pipeline paused — awaiting approval", extra={"run_id": run_id})
        else:
            await update_run_status(run_id, "completed")
            await sse.push(run_id, {"node": "done", "status": "completed"})
            logger.info(
                "Pipeline completed — no obligations found", extra={"run_id": run_id}
            )

    except Exception as exc:
        logger.exception("Pipeline failed", extra={"run_id": run_id, "error": str(exc)})
        await update_run_status(run_id, "error", str(exc))
        await sse.push(run_id, {"node": "error", "status": "error", "detail": str(exc)})


async def _emit_run_metrics(
    run_id: str,
    final_state: Any,
    node_sequence: list[str],
    started_at: float,
) -> None:
    """Best-effort post-run metrics. Never raises — metrics failures must not
    surface as pipeline errors."""
    try:
        values = getattr(final_state, "values", None) or {}
        obligations = values.get("obligations") or []
        gap_results = values.get("gap_results") or []
        risk_scores = values.get("risk_scores") or []

        # A2A calls = 1 ingest + N risk scorings (one per gap that wasn't fast-pathed).
        a2a_calls = 1 + len(risk_scores)

        wall_ms = (time.monotonic() - started_at) * 1000.0
        metrics = compute_run_metrics(
            run_id=run_id,
            node_sequence=node_sequence,
            obligations_count=len(obligations),
            gap_results=gap_results,
            risk_scores=risk_scores,
            a2a_call_count=a2a_calls,
            pipeline_wall_ms=wall_ms,
        )
        await write_run_metrics(run_id, metrics)
    except Exception:
        logger.exception("run_metrics_emit_failed", extra={"run_id": run_id})


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

        from langgraph.types import Command as LangGraphCommand

        async with get_checkpointer() as checkpointer:
            graph = build_supervisor_graph(checkpointer)
            config = _build_runnable_config(run_id, operation="resume")

            resume_cmd: LangGraphCommand[Any] = LangGraphCommand(
                resume={"approved": approved, "edits": edits}
            )
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
