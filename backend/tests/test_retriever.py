import pytest

from app.graph.retriever import LexicalRetriever, get_retriever, load_knowledge_base


def test_knowledge_base_loads():
    chunks = load_knowledge_base()
    assert len(chunks) > 0
    sources = {c.source for c in chunks}
    assert "Approved Materials Catalog" in sources
    assert "Quantity and Minimum Order Policy" in sources


@pytest.mark.parametrize(
    "query,expected_source",
    [
        ("dimensional tolerance default millimetre panel", "Dimensional Tolerance Policy"),
        ("approved materials catalog fabric gsm supplier code", "Approved Materials Catalog"),
        ("minimum order quantity moq units surcharge", "Quantity and Minimum Order Policy"),
        ("finishing dyeing enzyme wash oeko-tex shrinkage", "Finishing and Treatment Standards"),
        ("fiber content care label country of origin regulatory", "Labeling and Regulatory Policy"),
    ],
)
def test_targeted_query_maps_to_right_policy(query, expected_source):
    hits = get_retriever().query(query, k=1)
    assert hits, "expected at least one hit"
    assert hits[0].source == expected_source


def test_scores_sorted_descending():
    hits = get_retriever().query("cotton material tolerance quantity", k=5)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_empty_query_returns_nothing():
    assert get_retriever().query("", k=3) == []


def test_unknown_terms_return_nothing():
    assert get_retriever().query("zzzqqq xyzzy nonsenseword", k=3) == []


def test_empty_retriever_does_not_crash():
    r = LexicalRetriever([])
    assert r.query("anything", k=3) == []


def test_chunker_keeps_body_when_no_blank_line_after_heading(tmp_path):
    # Heading immediately followed by body, no blank line between.
    (tmp_path / "p.md").write_text("# My Policy\nThe body text about widgets.\n", encoding="utf-8")
    chunks = load_knowledge_base(tmp_path)
    assert len(chunks) == 1
    assert chunks[0].source == "My Policy"
    assert "widgets" in chunks[0].text
