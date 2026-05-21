"""Runs router — POST /runs, GET /runs/{id}, POST /runs/{id}/approve, SSE /runs/{id}/events."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from reglens.api.deps import get_db, require_api_key
from reglens.persistence.models import Run
from reglens.schemas.report import ComplianceReport
from reglens.supervisor.checkpoint import get_checkpointer
from reglens.supervisor.graph import build_supervisor_graph
from reglens.supervisor.state import SupervisorState

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runs", tags=["runs"])

# In-memory SSE event queues per run_id.
# In production this would be replaced by a pub/sub mechanism.
_sse_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}


# ---------------------------------------------------------------------------
# POST /runs

class RunCreatedResponse(BaseModel):
    run_id: str
    status: str = "pending"


@router.post(
    "",
    response_model=RunCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
)
async def create_run(
    pdf: UploadFile,
    matrix: UploadFile,
    regulation_ref: str = "UNKNOWN",
    domain: str = "banking",
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> RunCreatedResponse:
    run_id = str(uuid.uuid4())
    pdf_bytes = await pdf.read()
    matrix_bytes = await matrix.read()

    run = Run(
        id=run_id,  # type: ignore[arg-type]
        status="pending",
        domain=domain,
        pdf_filename=pdf.filename,
        matrix_filename=matrix.filename,
    )
    db.add(run)
    await db.commit()

    _sse_queues[run_id] = asyncio.Queue()
    background_tasks.add_task(
        _run_pipeline,
        run_id=run_id,
        pdf_bytes=pdf_bytes,
        matrix_bytes=matrix_bytes,
        regulation_ref=regulation_ref,
        domain=domain,
    )
    return RunCreatedResponse(run_id=run_id)


# ---------------------------------------------------------------------------
# GET /runs/{id}

@router.get(
    "/{run_id}",
    dependencies=[Depends(require_api_key)],
)
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run_id": str(run.id),
        "status": run.status,
        "domain": run.domain,
        "pdf_filename": run.pdf_filename,
        "matrix_filename": run.matrix_filename,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# GET /runs/{id}/events (SSE)

@router.get(
    "/{run_id}/events",
    dependencies=[Depends(require_api_key)],
)
async def run_events(run_id: str) -> EventSourceResponse:
    queue = _sse_queues.get(run_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="No event stream for this run")

    async def generator() -> Any:
        while True:
            event = await queue.get()
            yield {"data": json.dumps(event)}
            if event.get("status") in ("completed", "rejected", "error", "awaiting_approval"):
                break

    return EventSourceResponse(generator())


# ---------------------------------------------------------------------------
# POST /runs/{id}/approve

class ApproveRequest(BaseModel):
    approved: bool
    edits: list[dict[str, Any]] = []


class ApproveResponse(BaseModel):
    run_id: str
    status: str


@router.post(
    "/{run_id}/approve",
    response_model=ApproveResponse,
    dependencies=[Depends(require_api_key)],
)
async def approve_run(
    run_id: str,
    body: ApproveRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> ApproveResponse:
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail=f"Run is in status '{run.status}', expected 'awaiting_approval'",
        )

    background_tasks.add_task(
        _resume_pipeline,
        run_id=run_id,
        approved=body.approved,
        edits=body.edits,
    )
    new_status = "resuming" if body.approved else "rejected"
    return ApproveResponse(run_id=run_id, status=new_status)


# ---------------------------------------------------------------------------
# GET /runs/{id}/report

@router.get(
    "/{run_id}/report",
    dependencies=[Depends(require_api_key)],
)
async def get_report(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Report not available — run status is '{run.status}'",
        )
    # Retrieve the final report from LangGraph checkpointer state
    async with get_checkpointer() as checkpointer:
        graph = build_supervisor_graph(checkpointer)
        config = {"configurable": {"thread_id": run_id}}
        state = await graph.aget_state(config)
        values = state.values
        if not values or "final_report" not in values:
            raise HTTPException(status_code=404, detail="Report not found in graph state")
        report_data: dict[str, Any] = values["final_report"]
        if isinstance(report_data, ComplianceReport):
            report_data = report_data.model_dump(mode="json")
        return report_data


# ---------------------------------------------------------------------------
# Background pipeline tasks

async def _push_event(run_id: str, event: dict[str, Any]) -> None:
    queue = _sse_queues.get(run_id)
    if queue:
        await queue.put(event)


async def _update_run_status(run_id: str, status: str, error: str | None = None) -> None:
    from reglens.persistence.db import async_session_factory

    async with async_session_factory() as session:
        run = await session.get(Run, run_id)
        if run:
            run.status = status  # type: ignore[assignment]
            if error:
                run.error_message = error  # type: ignore[assignment]
            await session.commit()


async def _run_pipeline(
    run_id: str,
    pdf_bytes: bytes,
    matrix_bytes: bytes,
    regulation_ref: str,
    domain: str,
) -> None:
    try:
        await _update_run_status(run_id, "running")
        await _push_event(run_id, {"node": "start", "status": "running"})

        initial_state: SupervisorState = {
            "run_id": run_id,
            "pdf_bytes": pdf_bytes,
            "matrix_path": "",
            "regulation_ref": regulation_ref,
            "domain": domain,
            "pdf_filename": "",
        }

        async with get_checkpointer() as checkpointer:
            graph = build_supervisor_graph(checkpointer)
            config = {"configurable": {"thread_id": run_id}}

            async for event in graph.astream(initial_state, config=config, stream_mode="values"):
                node_name = list(event.keys())[-1] if event else "unknown"
                await _push_event(run_id, {"node": node_name, "status": "running"})

        await _update_run_status(run_id, "awaiting_approval")
        await _push_event(run_id, {"node": "generate_report", "status": "awaiting_approval"})

    except Exception as exc:
        logger.exception("Pipeline error for run %s", run_id)
        await _update_run_status(run_id, "error", str(exc))
        await _push_event(run_id, {"node": "error", "status": "error", "detail": str(exc)})


async def _resume_pipeline(
    run_id: str,
    approved: bool,
    edits: list[dict[str, Any]],
) -> None:
    try:
        await _update_run_status(run_id, "running")
        await _push_event(run_id, {"node": "resume", "status": "running"})

        from langgraph.types import Command

        async with get_checkpointer() as checkpointer:
            graph = build_supervisor_graph(checkpointer)
            config = {"configurable": {"thread_id": run_id}}

            resume_cmd = Command(resume={"approved": approved, "edits": edits})
            async for event in graph.astream(resume_cmd, config=config, stream_mode="values"):
                node_name = list(event.keys())[-1] if event else "unknown"
                await _push_event(run_id, {"node": node_name, "status": "running"})

        final_status = "completed" if approved else "rejected"
        await _push_event(run_id, {"node": "done", "status": final_status})

    except Exception as exc:
        logger.exception("Resume error for run %s", run_id)
        await _update_run_status(run_id, "error", str(exc))
        await _push_event(run_id, {"node": "error", "status": "error", "detail": str(exc)})
