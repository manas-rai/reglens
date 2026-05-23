"""Shared classifier/scorer dispatch for behavioral tests.

Defaults to the deterministic stubs from evals.component.* so CI can run
without API keys. `LIVE_LLM=1` swaps in the real Claude/Gemini calls.

IMPORTANT: in stub mode the behavioral assertions are *harness smoke
tests* — they verify the eval plumbing (dataset loading, dispatch,
metric reporting) is wired correctly. They do NOT measure model
behavior because the stubs were tuned to satisfy these very cases.
Real signal only comes from LIVE_LLM=1.
"""

from __future__ import annotations

import os
import sys

from evals.component.gap_eval import _live_classify, _stub_classify
from evals.component.risk_eval import _live_score, _stub_score


def is_live() -> bool:
    return os.environ.get("LIVE_LLM") == "1"


def print_mode_banner(suite: str) -> None:
    if is_live():
        print(f"[{suite}] LIVE_LLM=1 — exercising real models.", file=sys.stderr)
    else:
        print(
            f"[{suite}] STUB MODE — assertions verify the harness, not the model.\n"
            f"          Set LIVE_LLM=1 for a real behavioral signal.",
            file=sys.stderr,
        )


def classify_gap(obligation_text: str, matched_policies: list[dict]) -> str:
    if is_live():
        return _live_classify(obligation_text, matched_policies)
    return _stub_classify(obligation_text, matched_policies)


def score_risk(item: dict) -> tuple[str, float]:
    if is_live():
        return _live_score(item)
    return _stub_score(item)
