"""Semantic policy retrieval using pgvector."""

from __future__ import annotations

import logging

from reglens.llm.gemini import embed_text
from reglens.persistence.db import async_session_factory
from reglens.rag.store import search_policies
from reglens.schemas.obligation import Obligation
from reglens.schemas.policy import Policy, PolicyMatch

logger = logging.getLogger(__name__)


async def retrieve_matching_policies(
    obligation: Obligation,
    k: int = 5,
) -> list[PolicyMatch]:
    """Find the top-k policies most semantically relevant to an obligation."""
    query = f"{obligation.clause}: {obligation.text}"
    embedding = await embed_text(query)

    async with async_session_factory() as session:
        rows = await search_policies(session, embedding, obligation.domain, k=k)

    matches: list[PolicyMatch] = []
    for row in rows:
        policy = Policy(
            id=row["id"],
            domain=row["domain"],
            section=row["section"],
            title=row["title"],
            text=row["text"],
            owner=row.get("owner"),
            tags=row.get("tags", "").split(",") if row.get("tags") else [],
        )
        matches.append(
            PolicyMatch(
                policy=policy,
                relevance_score=float(row["relevance"]),
                matched_obligation_id=obligation.id,
            )
        )
    return matches
