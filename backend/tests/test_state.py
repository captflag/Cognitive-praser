from app.graph.state import MAX_MESSAGES, append_bounded


def test_append_bounded_appends_list():
    assert append_bounded([{"a": 1}], [{"b": 2}]) == [{"a": 1}, {"b": 2}]


def test_append_bounded_wraps_single_dict():
    assert append_bounded([], {"a": 1}) == [{"a": 1}]


def test_append_bounded_handles_none_current():
    assert append_bounded(None, [{"a": 1}]) == [{"a": 1}]


def test_append_bounded_none_new_is_noop():
    assert append_bounded([{"a": 1}], None) == [{"a": 1}]


def test_append_bounded_caps_at_max():
    current = [{"i": i} for i in range(MAX_MESSAGES)]
    result = append_bounded(current, [{"i": 999}, {"i": 1000}])
    assert len(result) == MAX_MESSAGES
    # Oldest dropped, newest kept.
    assert result[-1] == {"i": 1000}
    assert {"i": 0} not in result
