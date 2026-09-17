import uuid

from app.graph.checkpoint import sync_checkpointer
from app.graph.graph import build_graph
from app.graph.state import MAX_MESSAGES

DOCS = [{"name": "e.txt", "kind": "email", "content": "Material: Linen\nQuantity: 900 units\nFinish: Washed"}]


def _cfg():
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


def test_run_pauses_at_gate():
    with sync_checkpointer() as saver:
        g = build_graph(saver)
        cfg = _cfg()
        g.invoke({"source_documents": DOCS}, cfg)
        snap = g.get_state(cfg)
        assert snap.next == ("final_dispatch",)
        assert "final_dispatch" not in snap.values
        assert snap.values["draft_rfq"]["status"] == "draft_pending_approval"
        assert set(snap.values["completed_agents"]) == {"ingestion", "compliance", "drafting"}


def test_resume_with_edits_dispatches():
    with sync_checkpointer() as saver:
        g = build_graph(saver)
        cfg = _cfg()
        g.invoke({"source_documents": DOCS}, cfg)
        g.update_state(cfg, {"human_edits": {"buyer_note": "approved"}})
        g.invoke(None, cfg)
        final = g.get_state(cfg)
        assert final.next == ()
        assert final.values["final_dispatch"]["rfq"]["buyer_note"] == "approved"
        # Edits were injected, so status reflects an edited approval.
        assert final.values["approval_status"] == "edited"


def test_messages_stay_bounded():
    with sync_checkpointer() as saver:
        g = build_graph(saver)
        cfg = _cfg()
        g.invoke({"source_documents": DOCS}, cfg)
        snap = g.get_state(cfg)
        assert len(snap.values.get("messages", [])) <= MAX_MESSAGES


def test_completed_agents_not_duplicated_on_resume():
    with sync_checkpointer() as saver:
        g = build_graph(saver)
        cfg = _cfg()
        g.invoke({"source_documents": DOCS}, cfg)
        g.invoke(None, cfg)
        final = g.get_state(cfg)
        # Each worker recorded exactly once (resume must not re-run them).
        completed = final.values["completed_agents"]
        assert sorted(completed) == ["compliance", "drafting", "ingestion"]
