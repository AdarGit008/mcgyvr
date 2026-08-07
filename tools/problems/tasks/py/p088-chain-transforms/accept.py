from solution import chain_transforms

GRID = [[1, 2, 3], [4, 5, 6]]

assert chain_transforms(GRID, ["cw"]) == [[4, 1], [5, 2], [6, 3]], "quarter turn clockwise"
assert chain_transforms(GRID, ["ccw"]) == [
    [3, 6],
    [2, 5],
    [1, 4],
], "quarter turn counterclockwise"
assert chain_transforms(GRID, ["mirror"]) == [[3, 2, 1], [6, 5, 4]], "left-right flip"
assert chain_transforms(GRID, ["flip"]) == [[4, 5, 6], [1, 2, 3]], "top-bottom flip"
assert chain_transforms(GRID, ["diag"]) == [
    [1, 4],
    [2, 5],
    [3, 6],
], "main-diagonal reflection"
assert chain_transforms(GRID, ["cw", "cw"]) == [[6, 5, 4], [3, 2, 1]], "two turns"
assert chain_transforms(GRID, ["cw", "flip"]) == [
    [6, 3],
    [5, 2],
    [4, 1],
], "steps compose in the order given"
assert chain_transforms(GRID, ["diag", "mirror"]) == [
    [4, 1],
    [5, 2],
    [6, 3],
], "reflection then mirror equals one clockwise turn"
assert chain_transforms(GRID, []) == [[1, 2, 3], [4, 5, 6]], "the empty chain is a copy"
assert GRID == [[1, 2, 3], [4, 5, 6]], "the argument grid is never modified"


def rejects(grid, steps):
    try:
        chain_transforms(grid, steps)
    except ValueError:
        return True
    return False


assert rejects(GRID, ["spin"]), "an unknown step is rejected"
assert rejects([], ["cw"]), "a grid with no rows is rejected"
assert rejects([[1, 2], [3]], ["cw"]), "ragged rows are rejected"
print("ok")
