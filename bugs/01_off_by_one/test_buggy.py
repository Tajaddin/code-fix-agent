from buggy import sum_first_n


def test_one():
    assert sum_first_n(1) == 1


def test_small():
    assert sum_first_n(5) == 15


def test_ten():
    assert sum_first_n(10) == 55


def test_zero():
    assert sum_first_n(0) == 0
