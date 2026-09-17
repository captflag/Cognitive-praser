from app.graph.agents import (
    compliance_agent,
    drafting_agent,
    final_dispatch,
    ingestion_agent,
)

DOCS = [{"name": "e.txt", "kind": "email", "content": "Material: Wool\nQuantity: 800 units\nFinish: Milled"}]


def test_ingestion_stub_extracts_and_labels_engine():
    out = ingestion_agent({"source_documents": DOCS})
    specs = out["raw_specifications"]
    assert specs["ingestion_engine"] == "stub"
    assert specs["source_document_count"] == 1
    assert "parsed_at" in specs
    assert out["completed_agents"] == ["ingestion"]


def test_ingestion_handles_no_documents():
    out = ingestion_agent({})
    assert out["raw_specifications"]["source_document_count"] == 0


def test_compliance_agent_returns_evidence():
    specs = ingestion_agent({"source_documents": DOCS})["raw_specifications"]
    out = compliance_agent({"raw_specifications": specs})
    assert isinstance(out["compliance_notes"], list) and out["compliance_notes"]
    assert "grade" in out["compliance_evidence"]
    assert out["completed_agents"] == ["compliance"]


def test_drafting_includes_evidence_and_parsed_by():
    specs = {"material": "Wool", "dimensions": "x", "quantity": "800 units", "finish": "Milled",
             "ingestion_engine": "stub"}
    out = drafting_agent({
        "raw_specifications": specs,
        "compliance_notes": ["note"],
        "compliance_evidence": {"grade": {"top_score": 0.1, "relevant": True}},
    })
    draft = out["draft_rfq"]
    assert draft["parsed_by"] == "stub"
    assert draft["compliance_evidence"]["grade"]["relevant"] is True
    assert draft["line_items"][0]["description"] == "Wool"
    assert out["approval_status"] == "pending"


def test_final_dispatch_applies_human_edits():
    draft = {"line_items": [{"quantity": "800 units"}], "status": "draft_pending_approval"}
    out = final_dispatch({"draft_rfq": draft, "human_edits": {"buyer_note": "ok", "quantity": "override"}})
    dispatched = out["final_dispatch"]["rfq"]
    assert dispatched["status"] == "dispatched_to_suppliers"
    assert dispatched["buyer_note"] == "ok"
    assert dispatched["quantity"] == "override"
    assert out["final_dispatch"]["applied_human_edits"] is True
    assert out["approval_status"] == "edited"


def test_final_dispatch_without_edits():
    out = final_dispatch({"draft_rfq": {"line_items": []}})
    assert out["final_dispatch"]["applied_human_edits"] is False
    assert out["approval_status"] == "approved"
