from solution import grid_determinant

assert grid_determinant([[7]]) == 7, "one cell"
assert grid_determinant([[0]]) == 0, "one empty cell"
assert grid_determinant([[3, 4], [5, 6]]) == -2, "two rows"
assert grid_determinant([[1, 2], [2, 4]]) == 0, "two rows in proportion"
assert grid_determinant([[-2, 3], [4, -6]]) == 0, "negatives in proportion"
assert grid_determinant([[1, 0, 0], [0, 1, 0], [0, 0, 1]]) == 1, "the plain grid"
assert grid_determinant([[0, 1, 0], [1, 0, 0], [0, 0, 1]]) == -1, "rows exchanged"
assert grid_determinant([[1, 2, 3], [4, 5, 6], [7, 8, 10]]) == -3, "three rows"
assert grid_determinant([[1, 2, 3], [4, 5, 6], [7, 8, 9]]) == 0, "rows stack flat"
assert grid_determinant([[2, -3, 1], [2, 0, -1], [1, 4, 5]]) == 49, "mixed signs"


def rejects(grid):
    try:
        grid_determinant(grid)
    except ValueError:
        return True
    return False


assert rejects([]), "no rows rejected"
assert rejects("g"), "non-list rejected"
assert rejects([[1, 2], [3]]), "ragged rows rejected"
assert rejects([[1, 2, 3], [4, 5, 6]]), "non-square rejected"
assert rejects([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]), "four rows"
assert rejects([[1, 2], [3, 4.5]]), "fraction rejected"
assert rejects([[1, "a"], [2, 3]]), "text cell rejected"
print("ok")
