# Cognitive RFQ & Tech-Pack Parsing Engine

A multi-agent system that turns messy, unstructured procurement inputs (2D manufacturing
drawings, textile tech-packs, scattered email threads) into a clean, standardized
**Request for Quotation (RFQ)** — with a **human-in-the-loop approval gate** before
anything is dispatched to suppliers.

Built on **LangGraph** (Supervisor pattern) + **FastAPI** + **React/Next.js**, designed
to run durably on **Supabase/Postgres** checkpoints in production and on **SQLite**
locally with zero external services.

## Why this architecture

| Pattern | Where | Why it matters |
|---|---|---|
| **Supervisor routing** | `app/graph/supervisor.py` | Deterministic orchestration of specialized worker agents instead of a fragile linear chain |
| **Durable HITL** | `interrupt_before=["final_dispatch"]` | Graph pauses before the irreversible supplier dispatch, persists full state, and resumes hours later on human approval |
| **Bounded state reducers** | `app/graph/state.py` | Caps token/context bloat — the #1 cost killer in multi-agent systems |
| **Checkpointer abstraction** | `app/graph/checkpoint.py` | SQLite for local dev, Postgres (Supabase) for prod — same graph code |

## Build roadmap

- [x] **Step 1 — Supervisor + durable HITL loop** (stub agents, SQLite)
- [x] **Step 2 — React/Next.js approval dashboard** (review → edit → resume)
- [x] **Step 3 — Gemini multimodal ingestion** (parse drawings/tech-packs/PDFs; stub fallback)
- [x] **Step 4 — Corrective-RAG compliance** (retrieve → grade → self-correct → grounded notes) ← *you are here*

The HITL loop is built **first, on purpose**: it's the hardest and most impressive part,
so even a half-finished project demos well.

## Corrective RAG (Step 4)

The compliance agent (`app/graph/crag.py`) runs a **retrieve → grade → correct → generate**
loop against a local policy knowledge base (`backend/knowledge/*.md`):

- **Retrieve** with a zero-setup, dependency-free TF-IDF cosine retriever (`retriever.py`).
- **Grade** the top result; if it's below the relevance threshold, **self-correct** by
  expanding the query and retrieving again (the `corrected` flag records this).
- **Generate** notes that cite *only* policies actually retrieved — grounded, not
  hallucinated. The dashboard shows the retrieved sources, their scores, and the grade.

Swapping the retriever for Supabase pgvector or Gemini embeddings touches only
`retriever.py`.

## Quick start (backend)

```bash
cd backend
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# Git Bash:            source .venv/Scripts/activate
pip install -r requirements.txt

# Prove the full pause/approve/resume loop from the CLI (no API keys needed):
python -m scripts.demo_hitl

# Or run the API server:
uvicorn app.server:app --reload
```

## Quick start (frontend)

Run the backend first (`uvicorn app.server:app --reload`), then in another terminal:

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

The dashboard: paste an email/tech-pack → **Parse → Draft RFQ** (agents run, graph pauses
at the approval gate) → edit fields / add a buyer note → **Approve & dispatch** (resumes
the graph) or **Reject**. Point it at a different backend via `NEXT_PUBLIC_API_BASE`.

## Tests

```bash
cd backend && ./.venv/Scripts/python.exe -m pytest -q
```

Covers state reducers, the lexical retriever, the CRAG loop (grounding, MOQ rules,
self-correction), each agent node, the compiled graph (pause/resume, bounded state,
no-duplicate-work on resume), and every API endpoint (incl. 404/409/400 edge cases).

## API (server)

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/runs` | Start a run; executes agents and **pauses** at the approval gate. Returns the draft RFQ + `thread_id`. |
| `GET` | `/runs/{thread_id}` | Fetch current draft + approval status. |
| `POST` | `/runs/{thread_id}/approve` | Inject optional human edits and **resume** → dispatches the RFQ. |
| `POST` | `/runs/{thread_id}/reject` | Reject the draft. |

## Production notes

- Set `DATABASE_URL` (Supabase Postgres connection string) to switch checkpoints from
  SQLite to `AsyncPostgresSaver` with zero code changes.
- On the very first Postgres run, call `await saver.setup()` once (handled in
  `checkpoint.py`) to create the checkpoint tables.
- **SQLite is for local/single-user dev only.** The async path enables WAL + a busy
  timeout to soften "database is locked", but a concurrent production server should use
  Postgres via `DATABASE_URL`.
