"""Document ingestion agent — extract obligations from a PDF using Gemini multimodal."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from google.genai import types as genai_types

from evals.guards.llm_guards import check_obligation_density
from reglens.agents.ingestion.prompts import SYSTEM_PROMPT
from reglens.errors import IngestionError, LLMEmptyResponseError
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


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers Gemini sometimes adds."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]  # drop opening fence line
        if text.endswith("```"):
            text = text[: text.rfind("```")]
    return text.strip()


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
        max_output_tokens=65536,
    )

    if not raw:
        raise LLMEmptyResponseError(
            "Gemini returned an empty response during ingestion."
        )

    cleaned = _strip_markdown_fences(raw)
    try:
        items: list[dict[str, Any]] = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Gemini returned non-JSON ingestion output:\n%s", cleaned[:500])
        raise IngestionError(
            f"Could not parse obligation JSON from LLM output: {exc}"
        ) from exc

    try:
        obligations = [Obligation.model_validate(item) for item in items]
    except Exception as exc:
        raise IngestionError(f"Obligation schema validation failed: {exc}") from exc

    # L1 guard — use max(page) from extracted obligations as a proxy for
    # document length when no explicit page count is available.
    inferred_pages = max((o.page or 0 for o in obligations), default=0) or None
    check_obligation_density(obligations, inferred_pages).emit()

    logger.info("Extracted %d obligations from %s", len(obligations), regulation_ref)
    return obligations
