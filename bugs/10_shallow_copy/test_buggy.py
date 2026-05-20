from buggy import deduplicate_grids


def test_dedupe_one_grid():
    grids = [[1, 2, 2, 3]]
    out = deduplicate_grids(grids)
    assert out == [[1, 2, 3]]


def test_does_not_mutate_input_list():
    grids = [[1, 2, 2, 3]]
    snapshot = [list(g) for g in grids]
    deduplicate_grids(grids)
    assert grids == snapshot, "input list of grids must not be mutated"


def test_output_grids_are_separate_objects():
    grids = [[1, 2, 3]]
    out = deduplicate_grids(grids)
    assert out[0] is not grids[0], "output grid must not share identity with input"
