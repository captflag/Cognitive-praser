from app.graph.crag import _parse_qty, run_crag


def _textile_specs(**over):
    base = {
        "material": "Organic cotton jersey, 240 gsm",
        "dimensions": "600 x 900 mm",
        "quantity": "12000 units",
        "finish": "Garment-dyed",
    }
    base.update(over)
    return base


def test_parse_qty_variants():
    assert _parse_qty("12000 units") == 12000
    assert _parse_qty("1,200 units") == 1200
    assert _parse_qty("300units") == 300
    assert _parse_qty("") is None
    assert _parse_qty("no digits here") is None


def test_normal_specs_are_grounded():
    res = run_crag(_textile_specs())
    assert res["notes"]
    # Every note should cite a real policy, none flagged for manual review.
    assert not any("flagged for manual review" in n for n in res["notes"])
    assert res["evidence"]["grade"]["relevant"] is True


def test_moq_breach_flagged_below_500():
    res = run_crag(_textile_specs(quantity="300 units"))
    assert any("below the 500-unit MOQ" in n for n in res["notes"])


def test_volume_pricing_above_25000():
    res = run_crag(_textile_specs(quantity="40000 units"))
    assert any("volume pricing" in n for n in res["notes"])


def test_missing_tolerance_note_present():
    res = run_crag(_textile_specs(dimensions="600 x 900 mm"))  # no 'tol'
    assert any("tolerance" in n.lower() for n in res["notes"])


def test_tolerance_note_absent_when_specified():
    res = run_crag(_textile_specs(dimensions="600 x 900 mm, tol +/-2mm"))
    assert not any("Dimensional tolerance not stated" in n for n in res["notes"])


def test_self_correction_triggers_on_non_textile():
    res = run_crag({"material": "titanium alloy flange", "dimensions": "", "quantity": "", "finish": ""})
    assert res["evidence"]["corrected"] is True


def test_empty_specs_do_not_crash():
    res = run_crag({"material": "", "dimensions": "", "quantity": "", "finish": ""})
    assert isinstance(res["notes"], list)
    assert len(res["notes"]) >= 1  # labeling note is always present


def test_evidence_shape():
    ev = run_crag(_textile_specs())["evidence"]
    assert ev["engine"] == "lexical-tfidf"
    assert "grade" in ev and "top_score" in ev["grade"]
    assert isinstance(ev["sources"], list)
    for s in ev["sources"]:
        assert {"source", "score", "excerpt"} <= set(s)
