"""Tier 3 component evals — classical metrics per agent vs. labeled datasets.

These can all be executed as:
    uv run python -m evals.component.<eval_name>

Each script reads its dataset, computes metrics, prints a summary,
and exits non-zero if any threshold is missed.
"""
