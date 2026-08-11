from solution import row_widest, fold_rows

assert row_widest([[1], [1, 2, 3]]) == 3, "the longest row wins"
assert row_widest([]) == 0, "no rows at all"
assert fold_rows([[1], [1, 2, 3]]) == [
    [1, 0, 0],
    [1, 2, 3],
], "the short row is padded out"
assert fold_rows([]) == [], "no rows fold to no rows"
assert fold_rows([[1, 2], [3, 4]]) == [[1, 2], [3, 4]], "nothing needs padding"
assert fold_rows([[], [7]]) == [[0], [7]], "an empty row is padded"
print("ok")
