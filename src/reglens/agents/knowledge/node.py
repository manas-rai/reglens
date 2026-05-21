"""LangGraph knowledge node — retrieves policy matches for all obligations."""

from __future__ import annotations

import asyncio
import logging

from reglens.agents.knowledge.retriever import retrieve_matching_policies
from reglens.schemas.obligation import Obligation
from reglens.schemas.policy import PolicyMatch

logger = logging.getLogger(__name__)


async def retrieve_all_policies(
    obligations: list[Obligation],
    k: int = 5,
) -> dict[str, list[PolicyMatch]]:
    """Concurrently retrieve policy matches for all obligations.

    Returns a dict mapping obligation_id → list[PolicyMatch].
    """
    tasks = [retrieve_matching_policies(obl, k=k) for obl in obligations]
    results = await asyncio.gather(*tasks)
    mapping: dict[str, list[PolicyMatch]] = {}
    for obl, matches in zip(obligations, results, strict=True):
        mapping[obl.id] = matches
        logger.debug("Retrieved %d policies for %s", len(matches), obl.id)
    return mapping
