from solution import match_at, grid_find


def rejects(grid, value):
    try:
        grid_find(grid, value)
    except Exception:
        return True
    return False


assert match_at([[1]], 0, 0, 1) is True, "the cell holds it"
assert match_at([[1]], 0, 0, 2) is False, "the cell holds something else"
assert grid_find([[1, 2], [3, 4]], 4) == [1, 1], "the last cell"
assert grid_find([[1]], 1) == [0, 0], "the only cell"
assert grid_find([[1, 2], [2, 3]], 2) == [0, 1], "the first of two, read by row"
assert rejects([[1]], 9), "a value not in the grid is rejected"
print("ok")
