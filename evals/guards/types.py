"""Shared types for L1 guards."""

from __future__ import annotations

import logging
from enum import StrEnum

from opentelemetry import trace
from pydantic import BaseModel

logger = logging.getLogger("reglens.guards")


class GuardSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class GuardResult(BaseModel):
    """Result of a single guard check.

    `passed` is the binary signal. `metric_value` is the underlying number
    (e.g. relevance score, latency_ms) — recorded as an OTel span attribute
    so we can compute distributions over time.
    """

    name: str
    passed: bool
    severity: GuardSeverity = GuardSeverity.WARNING
    detail: str = ""
    metric_value: float | None = None

    def emit(self) -> None:
        """Record on the current OTel span and log if failed."""
        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute(f"guard.{self.name}.passed", self.passed)
            if self.metric_value is not None:
                span.set_attribute(f"guard.{self.name}.value", self.metric_value)
            if not self.passed:
                span.add_event(
                    f"guard.{self.name}.failed",
                    attributes={"detail": self.detail, "severity": self.severity},
                )

        if not self.passed:
            if self.severity is GuardSeverity.ERROR:
                logger.error(
                    "guard_failed",
                    extra={"guard": self.name, "detail": self.detail},
                )
            else:
                logger.warning(
                    "guard_failed",
                    extra={"guard": self.name, "detail": self.detail},
                )
