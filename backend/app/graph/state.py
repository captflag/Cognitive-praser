"""Graph state schema with bounded reducers.

The single biggest cost/latency killer in multi-agent systems is unbounded state:
every super-step appends to the context, tokens grow linearly, and the LLM context
window is eventually exhausted. We defend against that here with:

  * ``append_bounded`` — keeps only the last N messages (a sliding window), so the
    working transcript never grows past a fixed cap.
  * ``operator.add`` — used only for small, naturally-bounded lists (agent names,
    compliance notes).

Everything else uses LangGraph's default channel behaviour (last-write-wins).
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, Literal, TypedDict

# Sliding-window cap for the working transcript.
MAX_MESSAGES = 20


def append_bounded(current: list[dict[str, Any]] | None,
                   new: list[dict[str, Any]] | dict[str, Any] | None) -> list[dict[str, Any]]:
    """Reducer: append ``new`` message(s) and keep only the last ``MAX_MESSAGES``."""
    current = current or []
    if new is None:
        return current
    incoming = new if isinstance(new, list) else [new]
    combined = current + incoming
    return combined[-MAX_MESSAGES:]


ApprovalStatus = Literal["pending", "approved", "edited", "rejected"]


class RFQState(TypedDict, total=False):
    # --- Inputs ---
    source_documents: list[dict[str, Any]]     # raw ingested docs: {name, kind, content/path}

    # --- Working memory (bounded) ---
    messages: Annotated[list[dict[str, Any]], append_bounded]

    # --- Structured artifacts produced by worker agents ---
    raw_specifications: dict[str, Any]         # from the Ingestion agent
    compliance_notes: Annotated[list[str], add]  # from the Compliance agent
    compliance_evidence: dict[str, Any]        # CRAG retrieval + grade provenance
    draft_rfq: dict[str, Any]                  # from the Drafting agent

    # --- Routing ---
    next_agent: str
    completed_agents: Annotated[list[str], add]

    # --- Human-in-the-loop ---
    approval_status: ApprovalStatus
    human_edits: dict[str, Any]                # edits injected by the reviewer before dispatch
    final_dispatch: dict[str, Any]             # the committed, dispatched RFQ
