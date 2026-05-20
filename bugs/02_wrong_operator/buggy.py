def average(values: list[float]) -> float:
    """Return the arithmetic mean of a non-empty list of numbers."""
    if not values:
        raise ValueError("values must be non-empty")
    return sum(values) * len(values)
