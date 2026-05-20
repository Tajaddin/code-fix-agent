from buggy import safe_divide


def test_normal_division():
    assert safe_divide(10, 2) == 5.0


def test_zero_denominator_returns_zero():
    assert safe_divide(10, 0) == 0


def test_floats():
    assert safe_divide(1, 4) == 0.25
