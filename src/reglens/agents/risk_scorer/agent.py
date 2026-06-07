"""Risk scorer agent — assess regulatory risk for a gap result."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from evals.guards.llm_guards import check_risk_score_consistency
from reglens.agents.risk_scorer.prompts import SYSTEM_PROMPT
from reglens.errors import LLMEmptyResponseError, LLMValidationError
from reglens.llm.gemini import generate
from reglens.schemas.gap import GapResult, GapStatus
from reglens.schemas.risk import RiskLevel, RiskScore

logger = logging.getLogger(__name__)

RISK_MODEL = "gemini-2.5-flash"

_RUBRIC_PATH = (
    Path(__file__).parent.parent.parent / "domain" / "banking" / "risk_rubric.yaml"
)

_RISK_SCHEMA = {
    "type": "object",
    "properties": {
        "risk_level": {
            "type": "string",
            "enum": [r.value for r in RiskLevel],
        },
        "score": {"type": "number"},
        "justification": {"type": "string"},
        "regulatory_penalty_risk": {"type": "string"},
        "reputational_risk": {"type": "string"},
    },
    "required": ["risk_level", "score", "justification"],
}


def _load_rubric() -> str:
    with _RUBRIC_PATH.open() as f:
        return yaml.safe_dump(yaml.safe_load(f))


async def score_gap(gap_result: GapResult) -> RiskScore:
    """Score the regulatory risk for a single gap result."""
    if gap_result.status in (GapStatus.COMPLIANT, GapStatus.NOT_APPLICABLE):
        return RiskScore(
            gap_result=gap_result,
            risk_level=RiskLevel.NONE,
            score=0.0,
            justification="No gap — obligation is compliant or not applicable.",
        )

    rubric = _load_rubric()
    prompt = (
        f"Risk Rubric:\n{rubric}\n\n"
        f"Gap Result:\n{gap_result.model_dump_json(indent=2)}\n\n"
        "Assess the regulatory risk for this gap."
    )

    raw = await generate(
        model=RISK_MODEL,
        prompt=prompt,
        system_instruction=SYSTEM_PROMPT,
        response_schema=_RISK_SCHEMA,
    )

    if not raw:
        raise LLMEmptyResponseError(
            "Gemini returned an empty response during risk scoring."
        )

    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Risk scorer returned non-JSON: %s", raw[:200])
        raise LLMValidationError(
            f"Risk scorer returned non-JSON output: {exc}"
        ) from exc

    risk = RiskScore(
        gap_result=gap_result,
        risk_level=RiskLevel(data["risk_level"]),
        score=float(data["score"]),
        justification=data["justification"],
        regulatory_penalty_risk=data.get("regulatory_penalty_risk"),
        reputational_risk=data.get("reputational_risk"),
    )
    check_risk_score_consistency(risk).emit()
    return risk
