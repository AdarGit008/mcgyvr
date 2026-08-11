from solution import cell_at, diag_of

assert cell_at([[1, 2], [3, 4]], 0, 1) == 2, "a cell inside the grid"
assert cell_at([[1]], 5, 0) == 0, "a row outside the grid"
assert diag_of([[1, 2], [3, 4]]) == [1, 4], "the main diagonal"
assert diag_of([]) == [], "no rows, no diagonal"
assert diag_of([[1]]) == [1], "a grid of one cell"
assert diag_of([[1, 2, 3], [4, 5, 6]]) == [1, 5], "one step for each row"
print("ok")
