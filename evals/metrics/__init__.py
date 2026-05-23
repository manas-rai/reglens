"""Tier 1/2 metrics — computed after a pipeline run, written to audit_log."""

from evals.metrics.run_metrics import compute_run_metrics

__all__ = ["compute_run_metrics"]
