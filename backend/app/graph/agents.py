"""Worker agent nodes.

STEP 1: these are deterministic **stubs** so the whole Supervisor + HITL loop runs with
no API keys and no external services. Each stub has the same *shape* (signature and
returned state keys) that the real agent will have, so Steps 2–4 swap the body without
touching the graph wiring.

    Ingestion  -> parses source docs into raw_specifications        (Step 3: Gemini vision)
    Compliance -> checks specs against templates/rules              (Step 4: Corrective RAG)
    Drafting   -> compiles the structured draft_rfq

Node contract: take the full ``RFQState``, return a *partial* dict of updates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .crag import run_crag
from .ingestion import parse_with_gemini
from .state import RFQState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingestion_agent(state: RFQState) -> dict[str, Any]:
    """Extract raw specifications from unstructured source documents.

    Tries Gemini multimodal parsing first (drawings / tech-packs / PDFs / email text);
    falls back to a deterministic stub when no ``GOOGLE_API_KEY`` is configured, so the
    graph always runs.
    """
    docs = state.get("source_documents") or []

    specs = parse_with_gemini(docs)
    if specs is None:
        specs = _stub_extract(docs)

    specs.setdefault("ingestion_engine", "stub")
    specs["source_document_count"] = len(docs)
    specs["parsed_at"] = _now()

    return {
        "raw_specifications": specs,
        "completed_agents": ["ingestion"],
        "messages": [
            {"role": "ingestion", "content": f"Parsed {len(docs)} document(s) via {specs['ingestion_engine']}."}
        ],
    }


def _stub_extract(docs: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic fallback extractor over any text content in the documents."""
    text = " \n".join(str(d.get("content", "")) for d in docs)
    return {
        "material": _find(text, "material") or "Cotton twill, 280 gsm",
        "dimensions": _find(text, "dimension") or "A4 panel, 210 x 297 mm, tol +/-1mm",
        "quantity": _find(text, "quantity") or "5000 units",
        "finish": _find(text, "finish") or "Reactive dyed, pre-shrunk",
        "ingestion_engine": "stub",
    }


def compliance_agent(state: RFQState) -> dict[str, Any]:
    """Cross-reference the extracted specs against org policy via Corrective RAG.

    Retrieves relevant policy chunks, grades their relevance, self-corrects with an
    expanded query if the grade is weak, then generates notes grounded in the retrieved
    evidence (see ``crag.py``).
    """
    specs = state.get("raw_specifications") or {}
    result = run_crag(specs)
    grade = result["evidence"]["grade"]

    return {
        "compliance_notes": result["notes"],
        "compliance_evidence": result["evidence"],
        "completed_agents": ["compliance"],
        "messages": [
            {
                "role": "compliance",
                "content": (
                    f"CRAG: {len(result['notes'])} note(s); grade top_score="
                    f"{grade['top_score']} corrected={result['evidence']['corrected']}."
                ),
            }
        ],
    }


def drafting_agent(state: RFQState) -> dict[str, Any]:
    """Compile the structured, standardized RFQ document."""
    specs = state.get("raw_specifications") or {}
    notes = state.get("compliance_notes") or []
    evidence = state.get("compliance_evidence") or {}

    draft_rfq: dict[str, Any] = {
        "title": "Request for Quotation",
        "rfq_number": f"RFQ-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "line_items": [
            {
                "description": specs.get("material", ""),
                "dimensions": specs.get("dimensions", ""),
                "finish": specs.get("finish", ""),
                "quantity": specs.get("quantity", ""),
            }
        ],
        "compliance_notes": notes,
        "compliance_evidence": evidence,
        "parsed_by": specs.get("ingestion_engine", "stub"),
        "status": "draft_pending_approval",
        "drafted_at": _now(),
    }
    return {
        "draft_rfq": draft_rfq,
        "approval_status": "pending",
        "completed_agents": ["drafting"],
        "messages": [{"role": "drafting", "content": "Draft RFQ compiled; awaiting human approval."}],
    }


def final_dispatch(state: RFQState) -> dict[str, Any]:
    """Irreversible action: commit the (possibly human-edited) RFQ and dispatch to suppliers.

    The graph is compiled with ``interrupt_before=["final_dispatch"]``, so execution PAUSES
    before this node ever runs. It only executes after a human resumes the graph.
    """
    draft = dict(state.get("draft_rfq") or {})
    edits = state.get("human_edits") or {}
    draft.update(edits)  # apply reviewer edits on top of the draft
    draft["status"] = "dispatched_to_suppliers"

    dispatched = {
        "rfq": draft,
        "dispatched_at": _now(),
        "applied_human_edits": bool(edits),
    }
    return {
        "final_dispatch": dispatched,
        # Preserve whether the human edited the draft; don't flatten to "approved".
        "approval_status": "edited" if edits else "approved",
        "messages": [{"role": "system", "content": "RFQ dispatched to suppliers."}],
    }


def _find(text: str, key: str) -> str | None:
    """Tiny helper: return the remainder of the first line containing ``key`` (case-insensitive)."""
    for line in text.splitlines():
        if key.lower() in line.lower() and ":" in line:
            return line.split(":", 1)[1].strip()
    return None
