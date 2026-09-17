"""FastAPI server exposing the RFQ graph with a human-in-the-loop approval gate.

Run from backend/:

    uvicorn app.server:app --reload

Flow:
    POST /runs                     -> executes agents, pauses at the gate, returns draft
    POST /runs/upload              -> same, but accepts uploaded files (images/PDF/text)
    GET  /runs/{thread_id}         -> current draft + status
    POST /runs/{thread_id}/approve -> inject edits + resume -> dispatch
    POST /runs/{thread_id}/reject  -> mark rejected (no dispatch)
"""

from __future__ import annotations

import base64
import uuid
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .graph.checkpoint import async_checkpointer
from .graph.graph import build_graph

app = FastAPI(title="Cognitive RFQ Parser", version="0.1.0")

# Allow the local React/Next.js dev server to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class StartRunRequest(BaseModel):
    source_documents: list[dict[str, Any]]


class ApproveRequest(BaseModel):
    edits: dict[str, Any] | None = None


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


async def _start(source_documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a thread, run the agents until the approval gate, and return the draft."""
    thread_id = str(uuid.uuid4())
    config = _config(thread_id)

    async with async_checkpointer() as saver:
        graph = build_graph(saver)
        await graph.ainvoke({"source_documents": source_documents}, config)
        snapshot = await graph.aget_state(config)

    specs = snapshot.values.get("raw_specifications", {}) or {}
    return {
        "thread_id": thread_id,
        "status": snapshot.values.get("approval_status", "pending"),
        "paused_before": list(snapshot.next),
        "draft_rfq": snapshot.values.get("draft_rfq"),
        "compliance_notes": snapshot.values.get("compliance_notes", []),
        "ingestion_engine": specs.get("ingestion_engine", "stub"),
    }


@app.post("/runs")
async def start_run(req: StartRunRequest) -> dict[str, Any]:
    """Start a run from JSON source documents (text)."""
    return await _start(req.source_documents)


@app.post("/runs/upload")
async def start_run_upload(
    text: str = Form(default=""),
    files: list[UploadFile] = File(default=[]),
) -> dict[str, Any]:
    """Start a run from uploaded files (images / PDF / text) plus optional pasted text.

    Binary files are base64-encoded into the source document so the Gemini ingestion
    agent can pass them as multimodal parts. When no GOOGLE_API_KEY is set, only the
    text content contributes (the stub extractor ignores binary media).
    """
    source_documents: list[dict[str, Any]] = []
    if text.strip():
        source_documents.append({"name": "pasted_input.txt", "kind": "text", "content": text})

    for f in files:
        raw = await f.read()
        mime = f.content_type or ""
        if mime.startswith("image/"):
            kind = "image"
        elif mime == "application/pdf":
            kind = "pdf"
        else:
            kind = "text"

        if kind == "text":
            source_documents.append(
                {"name": f.filename, "kind": "text", "content": raw.decode("utf-8", "ignore")}
            )
        else:
            source_documents.append(
                {
                    "name": f.filename,
                    "kind": kind,
                    "mime_type": mime,
                    "data": base64.b64encode(raw).decode("ascii"),
                }
            )

    if not source_documents:
        raise HTTPException(status_code=400, detail="Provide text or at least one file")

    return await _start(source_documents)


@app.get("/runs/{thread_id}")
async def get_run(thread_id: str) -> dict[str, Any]:
    """Return the current draft and status for a run."""
    async with async_checkpointer() as saver:
        graph = build_graph(saver)
        snapshot = await graph.aget_state(_config(thread_id))

    if not snapshot.created_at:
        raise HTTPException(status_code=404, detail="Unknown thread_id")

    return {
        "thread_id": thread_id,
        "status": snapshot.values.get("approval_status", "pending"),
        "paused_before": list(snapshot.next),
        "draft_rfq": snapshot.values.get("draft_rfq"),
        "final_dispatch": snapshot.values.get("final_dispatch"),
    }


@app.post("/runs/{thread_id}/approve")
async def approve_run(thread_id: str, req: ApproveRequest) -> dict[str, Any]:
    """Inject optional human edits and resume the graph -> dispatches the RFQ."""
    config = _config(thread_id)

    async with async_checkpointer() as saver:
        graph = build_graph(saver)
        snapshot = await graph.aget_state(config)
        if not snapshot.created_at:
            raise HTTPException(status_code=404, detail="Unknown thread_id")
        if snapshot.values.get("approval_status") == "rejected":
            raise HTTPException(status_code=409, detail="Run was rejected and cannot be dispatched")
        if snapshot.next != ("final_dispatch",):
            raise HTTPException(status_code=409, detail="Run is not awaiting approval")

        await graph.aupdate_state(
            config,
            {"human_edits": req.edits or {}, "approval_status": "edited" if req.edits else "approved"},
        )
        await graph.ainvoke(None, config)  # resume from the interrupt point
        final = await graph.aget_state(config)

    return {
        "thread_id": thread_id,
        "status": final.values.get("approval_status"),
        "final_dispatch": final.values.get("final_dispatch"),
    }


@app.post("/runs/{thread_id}/reject")
async def reject_run(thread_id: str) -> dict[str, Any]:
    """Reject the draft without dispatching."""
    config = _config(thread_id)
    async with async_checkpointer() as saver:
        graph = build_graph(saver)
        snapshot = await graph.aget_state(config)
        if not snapshot.created_at:
            raise HTTPException(status_code=404, detail="Unknown thread_id")
        await graph.aupdate_state(config, {"approval_status": "rejected"})

    return {"thread_id": thread_id, "status": "rejected"}


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "Cognitive RFQ Parser", "docs": "/docs"}
