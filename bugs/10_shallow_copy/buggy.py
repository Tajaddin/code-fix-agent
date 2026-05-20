def deduplicate_grids(grids: list[list[int]]) -> list[list[int]]:
    """Return each grid with duplicates removed, preserving order.

    The input list must not be mutated, and each output grid must be a
    separate list from the input grid.
    """
    result = grids
    for i, grid in enumerate(grids):
        seen = []
        for value in grid:
            if value not in seen:
                seen.append(value)
        result[i] = seen
    return result
