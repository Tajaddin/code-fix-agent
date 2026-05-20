from buggy import CartTotal


def test_initial_total():
    cart = CartTotal()
    assert cart.total == 0.0


def test_single_add():
    cart = CartTotal()
    assert cart.add(5.0) == 5.0
    assert cart.total == 5.0


def test_accumulates():
    cart = CartTotal()
    cart.add(2.50)
    cart.add(7.50)
    assert cart.total == 10.0


def test_returns_running_total():
    cart = CartTotal()
    assert cart.add(1) == 1.0
    assert cart.add(2) == 3.0
    assert cart.add(3) == 6.0
