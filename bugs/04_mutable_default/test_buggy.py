from buggy import append_id


def test_first_call_returns_single_item():
    assert append_id("a") == ["a"]


def test_calls_are_independent():
    # Each call without a `log` arg must start from a fresh empty list.
    append_id("a")
    assert append_id("b") == ["b"]


def test_explicit_log_is_used():
    seed = ["x"]
    assert append_id("y", seed) == ["x", "y"]
