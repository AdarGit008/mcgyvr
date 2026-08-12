from solution import col_sum

assert col_sum([[1, 2], [3, 4]], 0) == 4, "the first column"
assert col_sum([[1, 2], [3, 4]], 1) == 6, "the second column"
assert col_sum([[1], [2, 3]], 1) == 3, "a short row adds nothing"
assert col_sum([], 0) == 0, "no rows at all"
assert col_sum([[]], 0) == 0, "a row holding nothing"
assert col_sum([[5]], 0) == 5, "one cell"
print("ok")
