"""Shared helpers for component evals: dataset loading, metric printing."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

DATASETS = Path(__file__).resolve().parent.parent / "datasets"


def load_dataset(rel_path: str) -> dict[str, Any]:
    return json.loads((DATASETS / rel_path).read_text())


def print_table(title: str, rows: list[tuple[str, Any]]) -> None:
    print(f"\n=== {title} ===")
    width = max(len(k) for k, _ in rows) if rows else 0
    for k, v in rows:
        if isinstance(v, float):
            v = f"{v:.3f}"
        print(f"  {k.ljust(width)}  {v}")


def assert_threshold(name: str, value: float, threshold: float) -> bool:
    ok = value >= threshold
    badge = "PASS" if ok else "FAIL"
    print(f"  [{badge}] {name}: {value:.3f} (threshold {threshold:.3f})")
    return ok


def exit_on_failure(failed: list[str]) -> None:
    if failed:
        print(f"\n{len(failed)} threshold(s) missed: {', '.join(failed)}")
        sys.exit(1)
    print("\nAll thresholds met.")
