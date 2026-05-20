import pytest

from buggy import average


def test_simple():
    assert average([1, 2, 3]) == 2.0


def test_floats():
    assert average([10.0, 20.0]) == 15.0


def test_single():
    assert average([42]) == 42


def test_empty_raises():
    with pytest.raises(ValueError):
        average([])
