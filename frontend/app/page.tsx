"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const SAMPLE_DOC = `Material: Organic cotton jersey, 240 gsm
Dimensions: Body panel 600 x 900 mm, tol +/-2mm
Quantity: 12000 units
Finish: Garment-dyed, enzyme washed`;

type LineItem = {
  description?: string;
  dimensions?: string;
  finish?: string;
  quantity?: string;
};

type EvidenceSource = { source: string; score: number; excerpt: string };
type ComplianceEvidence = {
  engine?: string;
  query?: string;
  corrected?: boolean;
  grade?: { top_score: number; relevant: boolean };
  sources?: EvidenceSource[];
};

type DraftRfq = {
  rfq_number?: string;
  line_items?: LineItem[];
  compliance_notes?: string[];
  compliance_evidence?: ComplianceEvidence;
  status?: string;
};

type Run = {
  thread_id: string;
  status: string;
  paused_before: string[];
  draft_rfq: DraftRfq | null;
  compliance_notes?: string[];
  ingestion_engine?: string;
  final_dispatch?: unknown;
};

export default function Dashboard() {
  const [docText, setDocText] = useState(SAMPLE_DOC);
  const [files, setFiles] = useState<File[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [item, setItem] = useState<LineItem>({});
  const [buyerNote, setBuyerNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const awaitingApproval = run?.paused_before?.includes("final_dispatch");
  const dispatched = Boolean(run?.final_dispatch);

  async function api<T>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) throw new Error(`${res.status} ${(await res.text()) || res.statusText}`);
    return res.json() as Promise<T>;
  }

  async function startRun() {
    setBusy(true);
    setError(null);
    setRun(null);
    try {
      let data: Run;
      if (files.length > 0) {
        // Multimodal path: send files (+ optional text) as multipart form data.
        const form = new FormData();
        if (docText.trim()) form.append("text", docText);
        files.forEach((f) => form.append("files", f));
        const res = await fetch(`${API_BASE}/runs/upload`, { method: "POST", body: form });
        if (!res.ok) throw new Error(`${res.status} ${(await res.text()) || res.statusText}`);
        data = await res.json();
      } else {
        data = await api<Run>("/runs", {
          source_documents: [{ name: "pasted_input.txt", kind: "email", content: docText }],
        });
      }
      setRun(data);
      setItem(data.draft_rfq?.line_items?.[0] ?? {});
      setBuyerNote("");
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!run) return;
    setBusy(true);
    setError(null);
    try {
      const edits: Record<string, unknown> = { line_items: [item] };
      if (buyerNote.trim()) edits.buyer_note = buyerNote.trim();
      const data = await api<Run>(`/runs/${run.thread_id}/approve`, { edits });
      setRun({ ...run, ...data, paused_before: [] });
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  async function reject() {
    if (!run) return;
    setBusy(true);
    setError(null);
    try {
      const data = await api<Run>(`/runs/${run.thread_id}/reject`);
      setRun({ ...run, ...data, paused_before: [] });
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="wrap">
      <header>
        <h1>Cognitive RFQ Parser</h1>
        <p>Multi-agent draft &rarr; human approval gate &rarr; dispatch to suppliers</p>
      </header>

      <section className="card">
        <h2>1 &middot; Source input</h2>
        <label>Paste an email / tech-pack text</label>
        <textarea value={docText} onChange={(e) => setDocText(e.target.value)} />

        <label>Or attach drawings / tech-packs / PDFs (parsed by Gemini when a key is set)</label>
        <input
          type="file"
          multiple
          accept="image/*,application/pdf,.txt"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
        {files.length > 0 && (
          <p className="meta">
            {files.length} file(s): {files.map((f) => f.name).join(", ")}
          </p>
        )}

        <div className="actions">
          <button className="btn-primary" onClick={startRun} disabled={busy}>
            {busy && !run ? "Running agents…" : "Parse → Draft RFQ"}
          </button>
        </div>
      </section>

      {run && (
        <section className="card">
          <h2>
            2 &middot; Draft RFQ{" "}
            <span className={`badge ${run.status}`}>{run.status}</span>
          </h2>

          {awaitingApproval && (
            <div className="gate">
              <span>&#9208;</span>
              <span>
                Graph paused at <code>interrupt_before=[&quot;final_dispatch&quot;]</code>. State
                persisted &mdash; nothing dispatched yet. Review, edit, then approve.
              </span>
            </div>
          )}

          <p className="meta">
            {run.draft_rfq?.rfq_number}
            {run.ingestion_engine && <>  &middot;  parsed by {run.ingestion_engine}</>}
          </p>

          <div className="row">
            <div>
              <label>Description</label>
              <input
                value={item.description ?? ""}
                onChange={(e) => setItem({ ...item, description: e.target.value })}
                disabled={!awaitingApproval}
              />
            </div>
            <div>
              <label>Dimensions</label>
              <input
                value={item.dimensions ?? ""}
                onChange={(e) => setItem({ ...item, dimensions: e.target.value })}
                disabled={!awaitingApproval}
              />
            </div>
            <div>
              <label>Finish</label>
              <input
                value={item.finish ?? ""}
                onChange={(e) => setItem({ ...item, finish: e.target.value })}
                disabled={!awaitingApproval}
              />
            </div>
            <div>
              <label>Quantity</label>
              <input
                value={item.quantity ?? ""}
                onChange={(e) => setItem({ ...item, quantity: e.target.value })}
                disabled={!awaitingApproval}
              />
            </div>
          </div>

          <label>Buyer note (optional edit injected on approval)</label>
          <input
            value={buyerNote}
            onChange={(e) => setBuyerNote(e.target.value)}
            placeholder="e.g. Split delivery: 50% in 30 days, 50% in 60 days"
            disabled={!awaitingApproval}
          />

          {(run.draft_rfq?.compliance_notes?.length ?? 0) > 0 && (
            <>
              <label>Compliance notes (Corrective RAG)</label>
              <ul className="notes">
                {run.draft_rfq?.compliance_notes?.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </>
          )}

          {run.draft_rfq?.compliance_evidence?.sources && (
            <>
              <label>
                Retrieval evidence &mdash; {run.draft_rfq.compliance_evidence.engine}
                {run.draft_rfq.compliance_evidence.grade && (
                  <>
                    {" "}
                    &middot; grade {run.draft_rfq.compliance_evidence.grade.top_score}{" "}
                    ({run.draft_rfq.compliance_evidence.grade.relevant ? "relevant" : "weak"})
                  </>
                )}
                {run.draft_rfq.compliance_evidence.corrected && "  ·  ↻ self-corrected"}
              </label>
              <ul className="notes">
                {run.draft_rfq.compliance_evidence.sources.map((s, i) => (
                  <li key={i}>
                    <strong>{s.source}</strong> <span className="meta">({s.score})</span> &mdash;{" "}
                    {s.excerpt}
                  </li>
                ))}
              </ul>
            </>
          )}

          {awaitingApproval && (
            <div className="actions">
              <button className="btn-approve" onClick={approve} disabled={busy}>
                {busy ? "Resuming…" : "Approve & dispatch"}
              </button>
              <button className="btn-reject" onClick={reject} disabled={busy}>
                Reject
              </button>
            </div>
          )}

          {error && <p className="error">Error: {error}</p>}
        </section>
      )}

      {dispatched && (
        <section className="card">
          <h2>3 &middot; Dispatched payload</h2>
          <pre>{JSON.stringify(run?.final_dispatch, null, 2)}</pre>
        </section>
      )}
    </div>
  );
}

function errText(e: unknown): string {
  const msg = e instanceof Error ? e.message : String(e);
  return msg.includes("Failed to fetch")
    ? "Cannot reach the API. Start the backend: uvicorn app.server:app --reload"
    : msg;
}
