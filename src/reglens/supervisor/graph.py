"""LangGraph supervisor graph — builds the StateGraph and compiles with checkpointer."""

from __future__ import annotations

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from reglens.supervisor.nodes import (
    node_analyze_gaps,
    node_empty_report,
    node_generate_report,
    node_ingest,
    node_retrieve_policies,
    node_score_risks,
)
from reglens.supervisor.routing import route_after_ingest
from reglens.supervisor.state import SupervisorState


def build_supervisor_graph(checkpointer: AsyncPostgresSaver) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Build and compile the compliance analysis StateGraph."""
    builder: StateGraph[SupervisorState, SupervisorState, SupervisorState] = StateGraph(
        SupervisorState
    )

    builder.add_node("ingest", node_ingest)
    builder.add_node("empty_report", node_empty_report)
    builder.add_node("retrieve_policies", node_retrieve_policies)
    builder.add_node("analyze_gaps", node_analyze_gaps)
    builder.add_node("score_risks", node_score_risks)
    builder.add_node("generate_report", node_generate_report)

    builder.add_edge(START, "ingest")
    # Short-circuit to empty_report when ingestion finds no obligations.
    builder.add_conditional_edges(
        "ingest",
        route_after_ingest,
        {"retrieve_policies": "retrieve_policies", "empty_report": "empty_report"},
    )
    builder.add_edge("empty_report", END)
    builder.add_edge("retrieve_policies", "analyze_gaps")
    builder.add_edge("analyze_gaps", "score_risks")
    builder.add_edge("score_risks", "generate_report")
    builder.add_edge("generate_report", END)

    # interrupt() is called inside node_generate_report itself — no interrupt_before needed
    return builder.compile(checkpointer=checkpointer)  # type: ignore[return-value]
