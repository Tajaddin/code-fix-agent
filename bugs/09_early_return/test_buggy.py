from buggy import first_even


def test_finds_first_even():
    assert first_even([1, 3, 4, 6]) == 4


def test_first_element_already_even():
    assert first_even([2, 3, 5]) == 2


def test_no_even_returns_none():
    assert first_even([1, 3, 5]) is None


def test_empty_returns_none():
    assert first_even([]) is None
