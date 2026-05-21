"""A2A server entrypoint for the risk scorer agent."""

from __future__ import annotations

import logging
import os
from typing import Any

import uvicorn

from reglens.a2a.card import AgentCapabilities, AgentCard, AgentSkill
from reglens.a2a.server import make_a2a_app
from reglens.agents.risk_scorer.agent import score_gap
from reglens.observability.logging import configure_logging
from reglens.schemas.gap import GapResult

logger = logging.getLogger(__name__)


async def handle_score_gap(params: dict[str, Any]) -> Any:
    """A2A handler: score a gap result."""
    gap_result = GapResult.model_validate(params["gap_result"])
    risk_score = await score_gap(gap_result)
    return risk_score.model_dump(mode="json")


def build_app() -> tuple[Any, int]:
    port = int(os.getenv("ADK_AGENT_PORT", "8002"))
    name = os.getenv("ADK_AGENT_NAME", "risk-scorer")

    card = AgentCard(
        name=name,
        description="Scores the regulatory risk level of a compliance gap using Gemini and a domain risk rubric.",
        url=f"http://localhost:{port}",
        capabilities=AgentCapabilities(),
        skills=[
            AgentSkill(
                id="score_gap",
                name="Score Gap",
                description="Assess risk level for a GapResult and return a RiskScore.",
            )
        ],
    )

    handlers = {"score_gap": handle_score_gap}
    return make_a2a_app(card, handlers), port


if __name__ == "__main__":
    configure_logging()
    app, port = build_app()
    uvicorn.run(app, host="0.0.0.0", port=port, log_config=None)
