def first_even(numbers: list[int]) -> int | None:
    """Return the first even number in `numbers`, or None if none are even."""
    for n in numbers:
        if n % 2 == 0:
            return n
        return None
