"""Multimodal ingestion via Gemini — with a graceful fallback.

The real ingestion agent parses unstructured procurement inputs (2D manufacturing
drawings, textile tech-packs, PDFs, email text) into structured specifications using
Gemini's multimodal understanding.

Key-optional by design:
  * If ``GOOGLE_API_KEY`` is set and the ``google-genai`` SDK is installed, we call
    Gemini with structured (JSON-schema) output.
  * Otherwise ``parse_with_gemini`` returns ``None`` and the agent falls back to the
    deterministic stub extractor — so the repo always runs for anyone who clones it.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from pydantic import BaseModel, Field

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

_PROMPT = (
    "You are a procurement analyst for a textile / contract-manufacturing firm. "
    "Extract a standardized specification from the attached documents, which may include "
    "2D manufacturing drawings, tech-packs, PDFs, and email threads. "
    "Read dimensions and tolerances from drawings when present. "
    "If a field is genuinely absent, leave it as an empty string. Do not invent values."
)


class RfqSpecs(BaseModel):
    """Structured specification Gemini returns (used as the response schema)."""

    material: str = Field(default="", description="Material / fabric and weight, e.g. 'Cotton twill, 280 gsm'")
    dimensions: str = Field(default="", description="Key dimensions with tolerances if shown on the drawing")
    quantity: str = Field(default="", description="Order quantity, e.g. '5000 units'")
    finish: str = Field(default="", description="Finishing / treatment requirements")
    notes: str = Field(default="", description="Any other buyer-relevant detail worth surfacing")


def parse_with_gemini(source_documents: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Parse documents with Gemini. Returns a specs dict, or ``None`` to signal fallback."""
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        # SDK not installed — behave exactly like "no key" so the stub takes over.
        return None

    contents: list[Any] = [_PROMPT]
    for doc in source_documents:
        kind = doc.get("kind")
        if kind in ("image", "pdf") and doc.get("data"):
            raw = base64.b64decode(doc["data"])
            contents.append(
                types.Part.from_bytes(
                    data=raw,
                    mime_type=doc.get("mime_type", "application/octet-stream"),
                )
            )
        elif doc.get("content"):
            contents.append(f"Document {doc.get('name', 'untitled')}:\n{doc['content']}")

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RfqSpecs,
                temperature=0,
            ),
        )
        text = response.text
        if not text:
            return None  # empty / safety-blocked response -> fall back to stub
        specs = json.loads(text)
    except Exception:
        # Any API/network/quota/parse error degrades gracefully to the stub extractor
        # rather than failing the whole run.
        return None

    specs["ingestion_engine"] = f"gemini:{GEMINI_MODEL}"
    return specs
