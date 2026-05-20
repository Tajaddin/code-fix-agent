from buggy import Counter


def test_starts_at_zero():
    c = Counter()
    assert c.get() == 0


def test_inc_returns_new_value():
    c = Counter()
    assert c.inc() == 1
    assert c.inc() == 2


def test_independent_instances():
    a = Counter()
    b = Counter()
    a.inc()
    a.inc()
    assert b.get() == 0
    assert a.get() == 2
