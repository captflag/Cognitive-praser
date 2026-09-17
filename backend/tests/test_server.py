import io

import pytest
from fastapi.testclient import TestClient

from app.server import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _start(client, content="Material: Cotton twill 280 gsm\nQuantity: 800 units\nFinish: Reactive dyed"):
    r = client.post("/runs", json={"source_documents": [{"name": "e", "kind": "email", "content": content}]})
    assert r.status_code == 200, r.text
    return r.json()


def test_start_run_pauses(client):
    j = _start(client)
    assert j["paused_before"] == ["final_dispatch"]
    assert j["draft_rfq"]["status"] == "draft_pending_approval"
    assert j["ingestion_engine"] == "stub"
    assert j["status"] == "pending"


def test_get_run_roundtrip(client):
    tid = _start(client)["thread_id"]
    r = client.get(f"/runs/{tid}")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"


def test_get_unknown_thread_404(client):
    r = client.get("/runs/does-not-exist")
    assert r.status_code == 404


def test_approve_applies_edits_and_dispatches(client):
    tid = _start(client)["thread_id"]
    r = client.post(f"/runs/{tid}/approve", json={"edits": {"buyer_note": "go", "quantity": "750 units"}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "edited"
    assert body["final_dispatch"]["rfq"]["buyer_note"] == "go"
    assert body["final_dispatch"]["rfq"]["quantity"] == "750 units"


def test_double_approve_conflicts(client):
    tid = _start(client)["thread_id"]
    assert client.post(f"/runs/{tid}/approve", json={}).status_code == 200
    assert client.post(f"/runs/{tid}/approve", json={}).status_code == 409


def test_reject(client):
    tid = _start(client)["thread_id"]
    r = client.post(f"/runs/{tid}/reject")
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


def test_reject_unknown_404(client):
    assert client.post("/runs/nope/reject").status_code == 404


def test_rejected_run_cannot_be_approved(client):
    tid = _start(client)["thread_id"]
    assert client.post(f"/runs/{tid}/reject").status_code == 200
    # A rejected RFQ must never be dispatchable via approve.
    r = client.post(f"/runs/{tid}/approve", json={})
    assert r.status_code == 409
    # And it must not have been dispatched.
    got = client.get(f"/runs/{tid}").json()
    assert got["final_dispatch"] is None


def test_approve_unknown_404(client):
    assert client.post("/runs/no-such-thread/approve", json={}).status_code == 404


def test_upload_text_file(client):
    files = {"files": ("techpack.txt", io.BytesIO(b"Material: Linen\nQuantity: 600 units"), "text/plain")}
    r = client.post("/runs/upload", files=files)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["paused_before"] == ["final_dispatch"]
    assert j["ingestion_engine"] == "stub"


def test_upload_empty_is_rejected(client):
    # No files, no text -> should not start a run.
    r = client.post("/runs/upload", data={"text": ""})
    assert r.status_code in (400, 422)
