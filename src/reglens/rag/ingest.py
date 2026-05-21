"""Load a control matrix YAML into the pgvector policies table."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from reglens.llm.gemini import embed_texts
from reglens.persistence.db import async_session_factory
from reglens.rag.store import upsert_policy
from reglens.schemas.policy import Policy

logger = logging.getLogger(__name__)


def _load_matrix(path: Path) -> list[Policy]:
    with path.open() as f:
        data: dict[str, Any] = yaml.safe_load(f)

    policies: list[Policy] = []
    for entry in data.get("policies", []):
        policies.append(Policy.model_validate(entry))
    return policies


async def ingest_matrix(matrix_path: Path) -> int:
    """Embed and upsert all policies from a YAML control matrix. Returns count."""
    policies = _load_matrix(matrix_path)
    if not policies:
        logger.warning("No policies found in %s", matrix_path)
        return 0

    texts = [f"{p.title}\n\n{p.text}" for p in policies]
    embeddings = await embed_texts(texts)

    async with async_session_factory() as session:
        for policy, embedding in zip(policies, embeddings, strict=True):
            await upsert_policy(session, policy, embedding)
        await session.commit()

    logger.info("Ingested %d policies from %s", len(policies), matrix_path)
    return len(policies)
