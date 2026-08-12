from solution import region_totals

GRID = [
    [1, 2, 3],
    [4, 5, 6],
    [7, 8, 9],
]

assert region_totals([[5]], [[0, 0, 1, 1]]) == [5], "single cell grid"
assert region_totals(GRID, [[0, 0, 3, 3]]) == [45], "the whole grid"
assert region_totals(GRID, [[0, 0, 1, 3]]) == [6], "the top row"
assert region_totals(GRID, [[1, 1, 3, 3]]) == [28], "an interior block"
assert region_totals(GRID, [[2, 2, 3, 3]]) == [9], "the bottom-right corner cell"
assert region_totals(GRID, [[0, 0, 3, 1], [0, 2, 3, 3], [1, 1, 2, 2]]) == [
    12,
    18,
    5,
], "several queries answer in order"
assert region_totals(GRID, []) == [], "no queries, no totals"
assert region_totals([[-2, 3], [4, -5]], [[0, 0, 2, 2]]) == [
    0
], "negative cells sum"


def rejects(grid, queries):
    try:
        region_totals(grid, queries)
    except Exception:
        return True
    return False


assert rejects([[1, 2], [3]], [[0, 0, 1, 1]]), "ragged rows are rejected"
assert rejects([], []), "an empty grid is rejected"
assert rejects([[1, 2.5]], [[0, 0, 1, 1]]), "a fractional cell is rejected"
assert rejects(GRID, [[0, 0, 1]]), "a three-bound query is rejected"
assert rejects(GRID, [[1, 0, 1, 3]]), "an empty block is rejected"
assert rejects(GRID, [[0, 0, 4, 3]]), "a query past the last row is rejected"
print("ok")
