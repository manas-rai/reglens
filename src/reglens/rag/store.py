"""pgvector policy store — upsert and semantic search."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from reglens.schemas.policy import Policy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ORM model for the policies table (defined in baseline migration)
# We reference it here via raw SQL to avoid duplicating the Vector column type
# in the declarative base — pgvector Column is already in the migration.

_INSERT_SQL = """
INSERT INTO policies (id, domain, section, title, text, owner, tags, embedding)
VALUES (:id, :domain, :section, :title, :text, :owner, :tags, :embedding)
ON CONFLICT (id) DO UPDATE
  SET domain = EXCLUDED.domain,
      section = EXCLUDED.section,
      title = EXCLUDED.title,
      text = EXCLUDED.text,
      owner = EXCLUDED.owner,
      tags = EXCLUDED.tags,
      embedding = EXCLUDED.embedding
"""

_SEARCH_SQL = """
SELECT id, domain, section, title, text, owner, tags,
       1 - (embedding <=> :query_vec::vector) AS relevance
FROM policies
WHERE domain = :domain
ORDER BY embedding <=> :query_vec::vector
LIMIT :k
"""


async def upsert_policy(session: AsyncSession, policy: Policy, embedding: list[float]) -> None:
    await session.execute(
        text(_INSERT_SQL),
        {
            "id": policy.id,
            "domain": policy.domain,
            "section": policy.section,
            "title": policy.title,
            "text": policy.text,
            "owner": policy.owner,
            "tags": ",".join(policy.tags),
            "embedding": str(embedding),
        },
    )


async def search_policies(
    session: AsyncSession,
    query_embedding: list[float],
    domain: str,
    k: int = 5,
) -> list[dict[str, Any]]:
    result = await session.execute(
        text(_SEARCH_SQL),
        {
            "query_vec": str(query_embedding),
            "domain": domain,
            "k": k,
        },
    )
    rows = result.mappings().all()
    return [dict(row) for row in rows]
