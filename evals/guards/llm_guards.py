"""Per-call guards for LLM outputs (ingestion, gap analyzer, risk scorer)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from evals.guards.types import GuardResult, GuardSeverity
from reglens.schemas.gap import GapResult, GapStatus
from reglens.schemas.risk import RiskLevel, RiskScore

if TYPE_CHECKING:
    from reglens.schemas.obligation import Obligation

MIN_REASONING_LEN = 40
MIN_OBLIGATION_DENSITY = 0.05  # obligations / page on a regulatory PDF

# Risk level <-> numeric score expected ranges (inclusive on lower bound).
_SCORE_BANDS: dict[RiskLevel, tuple[float, float]] = {
    RiskLevel.NONE: (0.0, 0.5),
    RiskLevel.LOW: (0.5, 4.0),
    RiskLevel.MEDIUM: (3.0, 7.0),
    RiskLevel.HIGH: (5.5, 9.0),
    RiskLevel.CRITICAL: (7.5, 10.0),
}


def check_obligation_density(
    obligations: list[Obligation], page_count: int | None
) -> GuardResult:
    """A dense regulatory PDF should yield at least ~0.05 obligations per page.

    If we know the page count and density is below threshold, flag potential
    sparse extraction. If page_count is unknown, return a pass (cannot judge).
    """
    if page_count is None or page_count <= 0:
        return GuardResult(
            name="ingestion.density",
            passed=True,
            detail="page count unknown — density not evaluable",
            metric_value=None,
        )

    density = len(obligations) / page_count
    passed = density >= MIN_OBLIGATION_DENSITY
    return GuardResult(
        name="ingestion.density",
        passed=passed,
        severity=GuardSeverity.WARNING,
        detail=(
            f"Sparse extraction: {len(obligations)} obligations / {page_count} pages "
            f"= {density:.3f} < {MIN_OBLIGATION_DENSITY}"
            if not passed
            else ""
        ),
        metric_value=density,
    )


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z]{4,}", text.lower()))


def check_gap_reasoning_grounding(gap: GapResult) -> GuardResult:
    """The reasoning must (a) be non-trivially long and (b) reference at least one
    distinctive token from the matched policies — otherwise it is likely a
    hallucination or boilerplate.

    Skipped for COMPLIANT/NOT_APPLICABLE with zero matches (no policies to cite).
    """
    reasoning = gap.reasoning or ""
    if len(reasoning) < MIN_REASONING_LEN:
        return GuardResult(
            name="gap.reasoning_grounding",
            passed=False,
            severity=GuardSeverity.WARNING,
            detail=f"reasoning too short ({len(reasoning)} chars)",
            metric_value=float(len(reasoning)),
        )

    if not gap.matched_policies:
        # Nothing to cite — skip the citation check, just record length.
        return GuardResult(
            name="gap.reasoning_grounding",
            passed=True,
            metric_value=float(len(reasoning)),
        )

    reasoning_toks = _tokenize(reasoning)
    policy_toks: set[str] = set()
    for match in gap.matched_policies:
        policy_toks |= _tokenize(match.policy.text)

    if not policy_toks:
        return GuardResult(
            name="gap.reasoning_grounding",
            passed=True,
            metric_value=float(len(reasoning)),
        )

    overlap = reasoning_toks & policy_toks
    passed = len(overlap) >= 2
    return GuardResult(
        name="gap.reasoning_grounding",
        passed=passed,
        severity=GuardSeverity.WARNING,
        detail=(
            f"reasoning cites <2 tokens from matched policies (overlap={len(overlap)})"
            if not passed
            else ""
        ),
        metric_value=float(len(overlap)),
    )


def check_risk_score_consistency(risk: RiskScore) -> GuardResult:
    """Score must fall within the expected band for its declared RiskLevel.

    Bands deliberately overlap at the seams — we only fail if the score
    falls clearly outside (e.g. CRITICAL with score=2.0).
    """
    band = _SCORE_BANDS.get(risk.risk_level)
    if band is None:
        return GuardResult(
            name="risk.score_consistency",
            passed=False,
            severity=GuardSeverity.ERROR,
            detail=f"unknown risk_level {risk.risk_level}",
        )

    low, high = band
    passed = low <= risk.score <= high
    return GuardResult(
        name="risk.score_consistency",
        passed=passed,
        severity=GuardSeverity.WARNING,
        detail=(
            f"score {risk.score} outside band {band} for level {risk.risk_level}"
            if not passed
            else ""
        ),
        metric_value=risk.score,
    )


def check_compliant_no_gap_description(gap: GapResult) -> GuardResult:
    """COMPLIANT or NOT_APPLICABLE must not carry a gap_description."""
    if gap.status in (GapStatus.COMPLIANT, GapStatus.NOT_APPLICABLE):
        passed = not gap.gap_description
        return GuardResult(
            name="gap.compliant_no_description",
            passed=passed,
            severity=GuardSeverity.WARNING,
            detail=(
                f"status={gap.status} but gap_description is populated"
                if not passed
                else ""
            ),
        )
    return GuardResult(name="gap.compliant_no_description", passed=True)
