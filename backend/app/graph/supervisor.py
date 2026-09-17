"""Supervisor routing.

Instead of letting worker agents call each other peer-to-peer (which invites infinite
loops and duplicated work), a single supervisor node inspects the shared state after
every step and decides which specialist runs next. Routing here is deterministic —
ingestion -> compliance -> drafting -> final_dispatch — which is exactly what you want
for an auditable procurement workflow.
"""

from __future__ import annotations

from typing import Any

from .state import RFQState

# The fixed pipeline of worker agents, in order.
WORKER_SEQUENCE = ["ingestion", "compliance", "drafting"]


def _route(state: RFQState) -> str:
    """Return the name of the next node to run given what has already completed."""
    done = set(state.get("completed_agents") or [])
    for name in WORKER_SEQUENCE:
        if name not in done:
            return name
    return "final_dispatch"


def supervisor(state: RFQState) -> dict[str, Any]:
    """Supervisor node: records the routing decision into state."""
    nxt = _route(state)
    return {
        "next_agent": nxt,
        "messages": [{"role": "supervisor", "content": f"Routing to: {nxt}"}],
    }


def route_edge(state: RFQState) -> str:
    """Conditional-edge function: reads the decision the supervisor just made."""
    return state["next_agent"]
