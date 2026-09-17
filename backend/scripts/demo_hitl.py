"""End-to-end demo of the durable human-in-the-loop loop — no API keys required.

Run from the backend/ directory:

    python -m scripts.demo_hitl

What it proves:
  1. A run starts and the supervisor drives ingestion -> compliance -> drafting.
  2. Execution PAUSES at the `final_dispatch` gate (interrupt_before) and the state is
     persisted to SQLite. Nothing has been dispatched.
  3. A human "reviews" the draft, injects an edit, and RESUMES the graph.
  4. The graph continues from exactly where it paused and dispatches the edited RFQ.
"""

from __future__ import annotations

import json
import uuid

from app.graph.checkpoint import sync_checkpointer
from app.graph.graph import build_graph

SAMPLE_DOCS = [
    {
        "name": "techpack_email.txt",
        "kind": "email",
        "content": (
            "Hi team, please quote the following.\n"
            "Material: Organic cotton jersey, 240 gsm\n"
            "Dimensions: Body panel 600 x 900 mm, tol +/-2mm\n"
            "Quantity: 12000 units\n"
            "Finish: Garment-dyed, enzyme washed\n"
        ),
    }
]


def _print_header(title: str) -> None:
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def main() -> None:
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    with sync_checkpointer() as saver:
        graph = build_graph(saver)

        # 1) Start the run — this executes until the interrupt_before gate.
        _print_header("STEP 1  Start run (executes agents, then PAUSES at approval gate)")
        graph.invoke({"source_documents": SAMPLE_DOCS}, config)

        snapshot = graph.get_state(config)
        print("Next node(s) queued:", snapshot.next, "  <- paused here, nothing dispatched")
        print("\nDraft RFQ awaiting approval:")
        print(json.dumps(snapshot.values.get("draft_rfq", {}), indent=2))

        assert snapshot.next == ("final_dispatch",), "Expected to pause before final_dispatch"
        assert "final_dispatch" not in snapshot.values, "Nothing should be dispatched yet"

        # 2) Human review — inject an edit, then resume.
        _print_header("STEP 2  Human injects an edit, then RESUMES the graph")
        human_edits = {"buyer_note": "Approved. Split delivery: 50% in 30 days, 50% in 60 days."}
        graph.update_state(config, {"human_edits": human_edits, "approval_status": "edited"})
        print("Injected human edit:", json.dumps(human_edits))

        # Resuming with input=None continues from the interrupt point.
        graph.invoke(None, config)

        final = graph.get_state(config)
        print("\nFinal approval status:", final.values.get("approval_status"))
        print("Dispatched payload:")
        print(json.dumps(final.values.get("final_dispatch", {}), indent=2))

        assert final.values.get("final_dispatch"), "RFQ should be dispatched after resume"
        assert final.next == (), "Graph should have run to completion"

    _print_header("SUCCESS  Durable pause -> human edit -> resume -> dispatch verified")
    print(f"(State persisted under thread_id={thread_id} in checkpoints.sqlite)")


if __name__ == "__main__":
    main()
