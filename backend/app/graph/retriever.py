"""Zero-setup lexical retriever over the compliance knowledge base.

A dependency-free TF-IDF + cosine retriever so Corrective RAG runs with no vector
database, no embeddings service, and no API key. The interface (``query`` returning
scored chunks) is deliberately the same shape a swap-in vector store would expose, so
upgrading to Supabase pgvector or Gemini embeddings later touches only this file.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass
class Chunk:
    source: str          # human-readable policy title
    text: str


@dataclass
class Hit:
    source: str
    text: str
    score: float


def load_knowledge_base(directory: Path = KNOWLEDGE_DIR) -> list[Chunk]:
    """Load every .md policy file and split it into paragraph chunks."""
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        title = path.stem.replace("_", " ").title()
        for para in raw.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            lines = para.splitlines()
            if lines[0].lstrip().startswith("#"):
                # Heading line: update the title and keep any body in the SAME block
                # (guards against a heading with no blank line before its text).
                title = lines[0].lstrip("# ").strip()
                body = "\n".join(lines[1:]).strip()
                if not body:
                    continue
                chunks.append(Chunk(source=title, text=body))
            else:
                chunks.append(Chunk(source=title, text=para))
    return chunks


class LexicalRetriever:
    """TF-IDF cosine retriever over a fixed set of chunks."""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        n = len(chunks)
        # Document frequency per term.
        df: dict[str, int] = {}
        tokenized = [_tokenize(c.text) for c in chunks]
        for toks in tokenized:
            for term in set(toks):
                df[term] = df.get(term, 0) + 1
        # Smoothed inverse document frequency.
        self.idf = {t: math.log((1 + n) / (1 + d)) + 1.0 for t, d in df.items()}
        # Pre-compute normalized tf-idf vectors for each chunk.
        self.vectors = [self._vectorize(toks) for toks in tokenized]

    def _vectorize(self, tokens: list[str]) -> dict[str, float]:
        tf: dict[str, float] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0.0) + 1.0
        vec = {t: c * self.idf.get(t, 0.0) for t, c in tf.items()}
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        return {t: w / norm for t, w in vec.items()}

    def query(self, text: str, k: int = 3) -> list[Hit]:
        qvec = self._vectorize(_tokenize(text))
        scored: list[Hit] = []
        for chunk, cvec in zip(self.chunks, self.vectors):
            # Cosine similarity of two already-normalized sparse vectors = dot product.
            small, large = (qvec, cvec) if len(qvec) < len(cvec) else (cvec, qvec)
            score = sum(w * large.get(t, 0.0) for t, w in small.items())
            if score > 0:
                scored.append(Hit(source=chunk.source, text=chunk.text, score=score))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:k]


@lru_cache(maxsize=1)
def get_retriever() -> LexicalRetriever:
    """Cached retriever so the knowledge base is loaded and vectorized once."""
    return LexicalRetriever(load_knowledge_base())
