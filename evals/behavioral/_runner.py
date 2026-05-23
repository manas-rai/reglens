"""Shared classifier/scorer dispatch for behavioral tests.

Defaults to the deterministic stubs from evals.component.* so CI can run
without API keys. `LIVE_LLM=1` swaps in the real Claude/Gemini calls.
"""

from __future__ import annotations

import os

from evals.component.gap_eval import _live_classify, _stub_classify
from evals.component.risk_eval import _live_score, _stub_score


def classify_gap(obligation_text: str, matched_policies: list[dict]) -> str:
    if os.environ.get("LIVE_LLM") == "1":
        return _live_classify(obligation_text, matched_policies)
    return _stub_classify(obligation_text, matched_policies)


def score_risk(item: dict) -> tuple[str, float]:
    if os.environ.get("LIVE_LLM") == "1":
        return _live_score(item)
    return _stub_score(item)
