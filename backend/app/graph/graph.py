r"""Assemble and compile the RFQ multi-agent graph.

    START -> supervisor --(conditional)--> {ingestion, compliance, drafting} -> supervisor
                              \--> final_dispatch -> END

The graph is compiled with ``interrupt_before=["final_dispatch"]`` so it pauses and
persists its full state right before the irreversible supplier dispatch — the
human-in-the-loop gate.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .agents import (
    compliance_agent,
    drafting_agent,
    final_dispatch,
    ingestion_agent,
)
from .state import RFQState
from .supervisor import route_edge, supervisor


def build_graph(checkpointer):
    """Build and compile the graph against a provided checkpointer.

    The checkpointer is injected so the same graph definition works with a SQLite saver
    (local dev / CLI) or an async Postgres saver (production server).
    """
    builder = StateGraph(RFQState)

    builder.add_node("supervisor", supervisor)
    builder.add_node("ingestion", ingestion_agent)
    builder.add_node("compliance", compliance_agent)
    builder.add_node("drafting", drafting_agent)
    builder.add_node("final_dispatch", final_dispatch)

    builder.add_edge(START, "supervisor")

    # Supervisor fans out to whichever worker (or the dispatch gate) is next.
    builder.add_conditional_edges(
        "supervisor",
        route_edge,
        {
            "ingestion": "ingestion",
            "compliance": "compliance",
            "drafting": "drafting",
            "final_dispatch": "final_dispatch",
        },
    )

    # Every worker reports back to the supervisor.
    builder.add_edge("ingestion", "supervisor")
    builder.add_edge("compliance", "supervisor")
    builder.add_edge("drafting", "supervisor")

    # Dispatch is terminal.
    builder.add_edge("final_dispatch", END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["final_dispatch"],  # <-- the durable HITL gate
    )
