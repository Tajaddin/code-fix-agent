from buggy import label


def test_basic():
    assert label(3, "Alice") == "#3 Alice"


def test_zero():
    assert label(0, "Bob") == "#0 Bob"


def test_long_name():
    assert label(42, "Charlie Brown") == "#42 Charlie Brown"
