"""Per-call guards for the A2A transport layer."""

from __future__ import annotations

from evals.guards.types import GuardResult, GuardSeverity

LATENCY_SLO_MS = 30_000.0  # 30 seconds — same as the A2A client default timeout
PAYLOAD_BLOAT_BYTES = 1_048_576  # 1 MiB


def check_a2a_latency(method: str, latency_ms: float) -> GuardResult:
    passed = latency_ms <= LATENCY_SLO_MS
    return GuardResult(
        name="a2a.latency",
        passed=passed,
        severity=GuardSeverity.WARNING,
        detail=(
            f"{method} took {latency_ms:.0f}ms > {LATENCY_SLO_MS:.0f}ms SLO"
            if not passed
            else ""
        ),
        metric_value=latency_ms,
    )


def check_a2a_payload_size(method: str, response_bytes: int) -> GuardResult:
    passed = response_bytes <= PAYLOAD_BLOAT_BYTES
    return GuardResult(
        name="a2a.payload_size",
        passed=passed,
        severity=GuardSeverity.WARNING,
        detail=(
            f"{method} response {response_bytes} bytes > {PAYLOAD_BLOAT_BYTES} budget"
            if not passed
            else ""
        ),
        metric_value=float(response_bytes),
    )
