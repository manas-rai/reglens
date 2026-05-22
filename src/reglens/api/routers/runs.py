"""Runs router — POST /runs, GET /runs/{id}, POST /runs/{id}/approve, SSE /runs/{id}/events."""

from __future__ import annotations

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
from sse_starlette.sse import EventSourceResponse

from reglens.api import sse
from reglens.api.deps import require_api_key
from reglens.persistence.db import db_session
from reglens.persistence.models import Run
from reglens.schemas.report import ComplianceReport
from reglens.schemas.run import (
    ApproveRequest,
    ApproveResponse,
    RunCreatedResponse,
    RunStatusResponse,
)
from reglens.supervisor.checkpoint import get_checkpointer
from reglens.supervisor.graph import build_supervisor_graph
from reglens.supervisor.pipeline import resume_pipeline, run_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runs", tags=["runs"])


@router.post(
    "",
    response_model=RunCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
)
async def create_run(
    pdf: UploadFile,
    regulation_ref: str = "UNKNOWN",
    domain: str = "banking",
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> RunCreatedResponse:
    run_id = str(uuid.uuid4())
    pdf_bytes = await pdf.read()

    async with db_session() as session:
        session.add(
            Run(
                id=run_id,  # type: ignore[arg-type]
                status="pending",
                domain=domain,
                pdf_filename=pdf.filename,
            )
        )

    logger.info(
        "Run created",
        extra={"run_id": run_id, "regulation_ref": regulation_ref, "domain": domain},
    )
    sse.register(run_id)
    background_tasks.add_task(
        run_pipeline,
        run_id=run_id,
        pdf_bytes=pdf_bytes,
        regulation_ref=regulation_ref,
        domain=domain,
    )
    return RunCreatedResponse(run_id=run_id)


@router.get(
    "/{run_id}",
    response_model=RunStatusResponse,
    dependencies=[Depends(require_api_key)],
)
async def get_run(run_id: str) -> RunStatusResponse:
    async with db_session() as session:
        run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunStatusResponse(
        run_id=str(run.id),
        status=run.status,
        domain=run.domain,
        pdf_filename=run.pdf_filename,
        error_message=run.error_message,
        created_at=run.created_at.isoformat(),
        updated_at=run.updated_at.isoformat(),
    )


@router.get(
    "/{run_id}/events",
    dependencies=[Depends(require_api_key)],
)
async def run_events(run_id: str) -> EventSourceResponse:
    queue = sse.get(run_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="No event stream for this run")

    async def generator() -> Any:
        while True:
            event = await queue.get()
            yield {"data": json.dumps(event)}
            if event.get("status") in (
                "completed",
                "rejected",
                "error",
                "awaiting_approval",
            ):
                break

    return EventSourceResponse(generator())


@router.post(
    "/{run_id}/approve",
    response_model=ApproveResponse,
    dependencies=[Depends(require_api_key)],
)
async def approve_run(
    run_id: str,
    body: ApproveRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> ApproveResponse:
    async with db_session() as session:
        run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail=f"Run is in status '{run.status}', expected 'awaiting_approval'",
        )

    logger.info(
        "Run approval received",
        extra={
            "run_id": run_id,
            "approved": body.approved,
            "edit_count": len(body.edits),
        },
    )
    background_tasks.add_task(
        resume_pipeline, run_id=run_id, approved=body.approved, edits=body.edits
    )
    new_status = "resuming" if body.approved else "rejected"
    return ApproveResponse(run_id=run_id, status=new_status)


@router.get(
    "/{run_id}/report",
    dependencies=[Depends(require_api_key)],
)
async def get_report(run_id: str) -> dict[str, Any]:
    async with db_session() as session:
        run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Report not available — run status is '{run.status}'",
        )

    async with get_checkpointer() as checkpointer:
        graph = build_supervisor_graph(checkpointer)
        state = await graph.aget_state({"configurable": {"thread_id": run_id}})
        values = state.values
        if not values or "final_report" not in values:
            raise HTTPException(
                status_code=404, detail="Report not found in graph state"
            )
        report_data: dict[str, Any] = values["final_report"]
        if isinstance(report_data, ComplianceReport):
            report_data = report_data.model_dump(mode="json")
        return report_data
