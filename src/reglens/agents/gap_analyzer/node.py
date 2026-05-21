"""LangGraph gap analyzer node — fan-out via Send()."""

from __future__ import annotations

import asyncio
import logging

from reglens.agents.gap_analyzer.analyzer import analyze_gap
from reglens.schemas.gap import GapResult
from reglens.schemas.obligation import Obligation
from reglens.schemas.policy import PolicyMatch

logger = logging.getLogger(__name__)

# Limit concurrent Claude calls to avoid rate limits
_CONCURRENCY = 5


async def analyze_all_gaps(
    obligations: list[Obligation],
    policy_matches: dict[str, list[PolicyMatch]],
) -> list[GapResult]:
    """Run gap analysis for all obligations concurrently (bounded concurrency)."""
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def _analyze_one(obligation: Obligation) -> GapResult:
        async with semaphore:
            matches = policy_matches.get(obligation.id, [])
            return await analyze_gap(obligation, matches)

    results = await asyncio.gather(*[_analyze_one(obl) for obl in obligations])
    return list(results)
