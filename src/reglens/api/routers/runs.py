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
    Query,
    UploadFile,
    status,
)
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from reglens.api import sse
from reglens.api.deps import require_api_key
from reglens.persistence.db import db_session
from reglens.persistence.models import AuditLog, CostRecord, Run
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
                id=run_id,
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
    "",
    dependencies=[Depends(require_api_key)],
)
async def list_runs(
    status_filter: str | None = Query(default=None, alias="status"),
    domain: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Paginated list of runs, newest first.

    Filters by status and/or domain when provided. Returns ``items`` plus the
    inputs that produced them so the UI can render pagination without extra
    bookkeeping.
    """
    stmt = select(Run).order_by(Run.created_at.desc())
    if status_filter:
        stmt = stmt.where(Run.status == status_filter)
    if domain:
        stmt = stmt.where(Run.domain == domain)
    stmt = stmt.limit(limit).offset(offset)
    async with db_session() as session:
        rows = (await session.execute(stmt)).scalars().all()
    items = [
        {
            "run_id": str(r.id),
            "status": r.status,
            "domain": r.domain,
            "pdf_filename": r.pdf_filename,
            "error_message": r.error_message,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        }
        for r in rows
    ]
    return {"items": items, "limit": limit, "offset": offset}


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


@router.get(
    "/{run_id}/audit",
    dependencies=[Depends(require_api_key)],
)
async def get_audit_log(run_id: str) -> dict[str, Any]:
    """Full audit_log rows for the run, oldest first."""
    async with db_session() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        rows = (
            (
                await session.execute(
                    select(AuditLog)
                    .where(AuditLog.run_id == run.id)
                    .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
                )
            )
            .scalars()
            .all()
        )
    items = [
        {
            "id": r.id,
            "node": r.node,
            "actor": r.actor,
            "payload": r.payload,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
    return {"items": items}


@router.get(
    "/{run_id}/costs",
    dependencies=[Depends(require_api_key)],
)
async def get_costs(run_id: str) -> dict[str, Any]:
    """Per-call cost records plus a total summary."""
    async with db_session() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        rows = (
            (
                await session.execute(
                    select(CostRecord)
                    .where(CostRecord.run_id == run.id)
                    .order_by(CostRecord.created_at.asc())
                )
            )
            .scalars()
            .all()
        )

    items = [
        {
            "id": r.id,
            "agent": r.agent,
            "model": r.model,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "cost_usd": float(r.cost_usd),
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
    total_cost = sum(float(r.cost_usd) for r in rows)
    total_prompt = sum(r.prompt_tokens for r in rows)
    total_completion = sum(r.completion_tokens for r in rows)
    return {
        "items": items,
        "total_cost_usd": total_cost,
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
    }


@router.get(
    "/{run_id}/gaps",
    dependencies=[Depends(require_api_key)],
)
async def get_gaps(run_id: str) -> dict[str, Any]:
    """Gap classifications from the graph state.

    Works at any point after the gap-analysis node has completed (mid-run,
    awaiting_approval, or completed) so the UI can render gaps before the
    final report is sealed.
    """
    async with db_session() as session:
        run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    async with get_checkpointer() as checkpointer:
        graph = build_supervisor_graph(checkpointer)
        state = await graph.aget_state({"configurable": {"thread_id": run_id}})
        values = state.values or {}
        gap_results = values.get("gap_results")
        if not gap_results:
            raise HTTPException(
                status_code=404,
                detail="Gap results not yet available for this run",
            )
        items: list[dict[str, Any]] = []
        for g in gap_results:
            items.append(g.model_dump(mode="json") if hasattr(g, "model_dump") else g)
    return {"items": items}
