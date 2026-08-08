from solution import triplet_sum_cells

assert triplet_sum_cells(
    [[0, 0, 1], [1, 2, 3]],
    [[0, 0, 4], [2, 1, -5]],
    3,
    3,
) == [
    [0, 0, 5],
    [1, 2, 3],
    [2, 1, -5],
], "shared cells add, lone cells carry through"

assert triplet_sum_cells([[0, 0, 7]], [[0, 0, -7]], 2, 2) == [
], "a cell that cancels is left out"

assert triplet_sum_cells([], [], 4, 4) == [], "two bare sheets overlay to nothing"

assert triplet_sum_cells([], [[2, 0, 9], [0, 3, 8]], 3, 4) == [
    [0, 3, 8],
    [2, 0, 9],
], "a bare sheet leaves the other one, reordered"

assert triplet_sum_cells(
    [[1, 1, 2], [0, 5, 1], [1, 0, 4]],
    [[1, 1, -2], [0, 5, 6]],
    2,
    6,
) == [
    [0, 5, 7],
    [1, 0, 4],
], "row order beats column order and the cancelled cell drops"

assert triplet_sum_cells(
    [[9999, 9999, 1000000000]], [[9999, 9999, -1]], 10000, 10000
) == [[9999, 9999, 999999999]], "the far corner and the mark limit both hold"


def rejects(*args):
    try:
        triplet_sum_cells(*args)
    except ValueError:
        return True
    return False


assert rejects([[0, 0, 1]], [[0, 0, 1]], 0, 3), "a shape with no rows is rejected"
assert rejects([[3, 0, 1]], [], 3, 3), "a row index at the edge is rejected"
assert rejects([[0, -1, 1]], [], 3, 3), "a negative column index is rejected"
assert rejects([[0, 0, 0]], [], 3, 3), "a stored mark of nothing is rejected"
assert rejects([[1, 1, 2], [1, 1, 3]], [], 3, 3), "a cell named twice is rejected"
assert rejects([[0, 0, 1.5]], [], 3, 3), "a fractional mark is rejected"
assert rejects([[0, 0, 1000000001]], [], 3, 3), "a mark past the limit is rejected"
assert rejects([[0, 0]], [], 3, 3), "an entry that is not a triple is rejected"
assert rejects("sheet", [], 3, 3), "a non-list sheet is rejected"
print("ok")
