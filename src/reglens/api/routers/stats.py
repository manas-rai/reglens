"""Stats router — aggregate metrics for the dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from reglens.api.deps import require_api_key
from reglens.persistence.db import db_session
from reglens.persistence.models import CostRecord, Run

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get(
    "",
    dependencies=[Depends(require_api_key)],
)
async def get_stats() -> dict[str, Any]:
    """Aggregates: total runs, run counts by status, total cost in USD.

    Cheap enough to recompute on every dashboard load; if it ever becomes a
    hot path, the natural next step is a materialised view, not a cache.
    """
    async with db_session() as session:
        total = (await session.execute(select(func.count(Run.id)))).scalar_one() or 0

        status_rows = (
            await session.execute(
                select(Run.status, func.count(Run.id)).group_by(Run.status)
            )
        ).all()
        by_status = {s: int(c) for s, c in status_rows}

        total_cost = (
            await session.execute(
                select(func.coalesce(func.sum(CostRecord.cost_usd), 0))
            )
        ).scalar_one()

    return {
        "total_runs": int(total),
        "by_status": by_status,
        "total_cost_usd": float(total_cost),
    }
