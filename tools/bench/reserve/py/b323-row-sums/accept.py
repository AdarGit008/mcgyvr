from solution import row_sums

assert row_sums([[1, 2], [3, 4]]) == [3, 7], "a row at a time"
assert row_sums([[]]) == [0], "an empty row totals nothing"
assert row_sums([]) == [], "no rows at all"
assert row_sums([[5]]) == [5], "a row of one"
assert row_sums([[1, 1, 1], [0]]) == [3, 0], "rows of different lengths"
assert row_sums([[-1, 1]]) == [0], "they cancel out"
print("ok")
