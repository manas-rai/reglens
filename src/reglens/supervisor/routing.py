"""Pure routing logic for the supervisor graph.

Kept in its own module (no LLM / DB / agent imports) so it can be unit-
and eval-tested without pulling in the full pipeline dependency tree.
"""

from __future__ import annotations

from reglens.supervisor.state import SupervisorState


def route_after_ingest(state: SupervisorState) -> str:
    """Route to retrieve_policies if obligations were found, else short-circuit to empty_report."""
    return "retrieve_policies" if state.get("obligations") else "empty_report"
