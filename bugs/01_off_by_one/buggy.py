def sum_first_n(n: int) -> int:
    """Return the sum of integers from 1 to n inclusive."""
    total = 0
    for i in range(n):
        total += i
    return total
