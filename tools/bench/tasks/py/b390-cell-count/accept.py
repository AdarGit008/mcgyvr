from solution import cell_count

assert cell_count([[1, 2], [2, 3]], 2) == 2, "twice across two rows"
assert cell_count([[1]], 9) == 0, "the value is absent"
assert cell_count([], 1) == 0, "no rows at all"
assert cell_count([[]], 1) == 0, "a row holding nothing"
assert cell_count([[1, 1], [1, 1]], 1) == 4, "every cell matches"
assert cell_count([[0]], 0) == 1, "a cell holding nothing still matches"
print("ok")
