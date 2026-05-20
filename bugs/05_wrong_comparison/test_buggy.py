from buggy import is_admin


def test_admin_true():
    assert is_admin("admin") is True


def test_user_false():
    assert is_admin("user") is False


def test_empty_false():
    assert is_admin("") is False
