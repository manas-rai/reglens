"""A2A server entrypoint for the document ingestion agent."""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

import uvicorn

from reglens.a2a.card import AgentCapabilities, AgentCard, AgentSkill
from reglens.a2a.server import make_a2a_app
from reglens.agents.ingestion.agent import extract_obligations
from reglens.observability.logging import configure_logging

logger = logging.getLogger(__name__)


async def handle_extract_obligations(params: dict[str, Any]) -> Any:
    """A2A handler: extract obligations from a base64-encoded PDF."""
    pdf_b64: str = params["pdf_b64"]
    regulation_ref: str = params["regulation_ref"]
    domain: str = params.get("domain", "banking")

    pdf_bytes = base64.standard_b64decode(pdf_b64)
    obligations = await extract_obligations(pdf_bytes, regulation_ref, domain)
    return [o.model_dump(mode="json") for o in obligations]


def build_app() -> Any:
    port = int(os.getenv("ADK_AGENT_PORT", "8001"))
    name = os.getenv("ADK_AGENT_NAME", "document-ingestion")

    card = AgentCard(
        name=name,
        description="Extracts structured regulatory obligations from PDF documents using Gemini multimodal.",
        url=f"http://localhost:{port}",
        capabilities=AgentCapabilities(),
        skills=[
            AgentSkill(
                id="extract_obligations",
                name="Extract Obligations",
                description="Parse a regulatory PDF and return structured Obligation objects.",
            )
        ],
    )

    handlers = {
        "extract_obligations": handle_extract_obligations,
    }

    return make_a2a_app(card, handlers), port


if __name__ == "__main__":
    configure_logging()
    app, port = build_app()
    uvicorn.run(app, host="0.0.0.0", port=port, log_config=None)
