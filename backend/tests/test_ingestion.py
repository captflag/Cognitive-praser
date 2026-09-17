import os

from app.graph.ingestion import RfqSpecs, parse_with_gemini


def test_parse_with_gemini_returns_none_without_key():
    os.environ.pop("GOOGLE_API_KEY", None)
    assert parse_with_gemini([{"name": "x", "kind": "text", "content": "Material: Wool"}]) is None


def test_gemini_failure_falls_back_to_none(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    from google import genai

    def boom(*args, **kwargs):
        raise RuntimeError("simulated API outage")

    monkeypatch.setattr(genai, "Client", boom)
    # Error must be swallowed so the agent can fall back to the stub.
    assert parse_with_gemini([{"name": "x", "kind": "text", "content": "Material: Wool"}]) is None


def test_rfqspecs_defaults_empty():
    s = RfqSpecs()
    assert s.material == ""
    assert s.dimensions == ""
    assert s.quantity == ""
    assert s.finish == ""
    assert s.notes == ""
