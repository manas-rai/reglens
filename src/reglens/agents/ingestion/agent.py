"""Document ingestion agent — extract obligations from a PDF using Gemini multimodal."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from google.genai import types as genai_types

from reglens.agents.ingestion.prompts import SYSTEM_PROMPT
from reglens.llm.gemini import generate_multimodal
from reglens.schemas.obligation import Obligation, ObligationType

logger = logging.getLogger(__name__)

INGESTION_MODEL = "gemini-2.5-pro"

# JSON schema passed to Gemini for structured output
_OBLIGATION_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "regulation_ref": {"type": "string"},
            "clause": {"type": "string"},
            "page": {"type": "integer"},
            "text": {"type": "string"},
            "obligation_type": {
                "type": "string",
                "enum": [t.value for t in ObligationType],
            },
            "domain": {"type": "string"},
            "effective_date": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["id", "regulation_ref", "clause", "text", "obligation_type"],
    },
}


async def extract_obligations(
    pdf_bytes: bytes,
    regulation_ref: str,
    domain: str = "banking",
) -> list[Obligation]:
    """Extract obligations from a regulatory PDF using Gemini multimodal."""
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()
    parts: list[genai_types.Part] = [
        genai_types.Part(
            inline_data=genai_types.Blob(data=pdf_b64, mime_type="application/pdf")
        ),
        genai_types.Part(
            text=(
                f"Regulation reference: {regulation_ref}\n"
                f"Domain: {domain}\n\n"
                "Extract all regulatory obligations from this document."
            )
        ),
    ]

    raw = await generate_multimodal(
        model=INGESTION_MODEL,
        parts=parts,
        system_instruction=SYSTEM_PROMPT,
        response_schema=_OBLIGATION_SCHEMA,
    )

    try:
        items: list[dict[str, Any]] = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Gemini returned non-JSON ingestion output: %s", raw[:200])
        raise

    obligations = [Obligation.model_validate(item) for item in items]
    logger.info(
        "Extracted %d obligations from %s", len(obligations), regulation_ref
    )
    return obligations
