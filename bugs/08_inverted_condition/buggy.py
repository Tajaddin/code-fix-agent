def safe_divide(a: float, b: float) -> float:
    """Return a/b, or 0 if b is zero."""
    if b:
        return 0
    return a / b
