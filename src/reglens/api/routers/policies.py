"""Policies router — read-only browse of the seeded RAG corpus."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from reglens.api.deps import require_api_key
from reglens.persistence.db import db_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/policies", tags=["policies"])


@router.get(
    "",
    dependencies=[Depends(require_api_key)],
)
async def list_policies(
    domain: str | None = None,
    q: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Paginated list of policy rows.

    ``q`` is an ILIKE substring match across id, title, and text — good
    enough for browsing the demo corpus. Semantic search uses pgvector via
    ``rag.store`` and isn't exposed here on purpose: this endpoint is for
    inventory, not retrieval.
    """
    where: list[str] = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if domain:
        where.append("domain = :domain")
        params["domain"] = domain
    if q:
        where.append("(id ILIKE :q OR title ILIKE :q OR text ILIKE :q)")
        params["q"] = f"%{q}%"
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    # WHERE fragments are constant strings built above; user input is bound
    # via :params (domain, q, limit, offset).
    sql = text(
        f"""
        SELECT id, domain, section, title, text, owner, tags, created_at
        FROM policies
        {where_clause}
        ORDER BY id ASC
        LIMIT :limit OFFSET :offset
        """  # noqa: S608
    )
    async with db_session() as session:
        result = await session.execute(sql, params)
        rows = result.mappings().all()
    items = [
        {
            "id": r["id"],
            "domain": r["domain"],
            "section": r["section"],
            "title": r["title"],
            "text": r["text"],
            "owner": r["owner"],
            "tags": r["tags"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]
    return {"items": items, "limit": limit, "offset": offset}


@router.get(
    "/{policy_id}",
    dependencies=[Depends(require_api_key)],
)
async def get_policy(policy_id: str) -> dict[str, Any]:
    sql = text(
        """
        SELECT id, domain, section, title, text, owner, tags, created_at
        FROM policies
        WHERE id = :id
        """
    )
    async with db_session() as session:
        result = await session.execute(sql, {"id": policy_id})
        row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {
        "id": row["id"],
        "domain": row["domain"],
        "section": row["section"],
        "title": row["title"],
        "text": row["text"],
        "owner": row["owner"],
        "tags": row["tags"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }
