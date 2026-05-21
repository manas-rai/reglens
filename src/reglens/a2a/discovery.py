"""Agent Card discovery with in-process LRU cache."""

from __future__ import annotations

import logging

import httpx

from reglens.a2a.card import AgentCard

logger = logging.getLogger(__name__)


async def fetch_agent_card(base_url: str) -> AgentCard:
    """Fetch and validate an Agent Card from a remote A2A server."""
    url = base_url.rstrip("/") + "/.well-known/agent-card.json"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
    card = AgentCard.model_validate(response.json())
    logger.info("Discovered agent card", extra={"agent": card.name, "url": base_url})
    return card
