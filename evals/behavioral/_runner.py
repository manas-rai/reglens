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

import logging
import os
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING

from evals.component.gap_eval import _live_classify, _stub_classify
from evals.component.risk_eval import _live_score, _stub_score

if TYPE_CHECKING:
    from collections.abc import Iterator


def is_live() -> bool:
    return os.environ.get("LIVE_LLM") == "1"


class GuardCapture(logging.Handler):
    """Capture L1 guard failures emitted on the 'reglens.guards' logger.

    Guards soft-fail by design (log + OTel event, never raise). For
    behavioral evals we want to surface those fires so a 'correct'
    classification arrived at via ungrounded reasoning is visible.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.fires: list[dict[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.getMessage() != "guard_failed":
            return
        self.fires.append(
            {
                "guard": str(getattr(record, "guard", "?")),
                "detail": str(getattr(record, "detail", "")),
            }
        )


@contextmanager
def capture_guards() -> Iterator[GuardCapture]:
    cap = GuardCapture()
    logger = logging.getLogger("reglens.guards")
    prev_level = logger.level
    logger.addHandler(cap)
    logger.setLevel(logging.WARNING)
    try:
        yield cap
    finally:
        logger.removeHandler(cap)
        logger.setLevel(prev_level)


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
