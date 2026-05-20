from buggy import last_item


def test_three_items():
    assert last_item([1, 2, 3]) == 3


def test_single_item():
    assert last_item(["only"]) == "only"


def test_empty_returns_none():
    assert last_item([]) is None
