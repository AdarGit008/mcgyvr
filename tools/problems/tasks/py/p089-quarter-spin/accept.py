from solution import quarter_spin

TILE = [[1, 2, 3], [4, 5, 6]]

assert quarter_spin(TILE, 1) == [[4, 1], [5, 2], [6, 3]], "one turn of a 2x3 grid"
assert TILE == [[1, 2, 3], [4, 5, 6]], "the argument grid is untouched"
assert quarter_spin(TILE, 2) == [[6, 5, 4], [3, 2, 1]], "two turns of a 2x3 grid"
assert quarter_spin(TILE, 3) == [[3, 6], [2, 5], [1, 4]], "three turns of a 2x3 grid"
assert quarter_spin(TILE, 0) == [[1, 2, 3], [4, 5, 6]], "zero turns is a plain copy"
assert quarter_spin(TILE, 4) == [[1, 2, 3], [4, 5, 6]], "four turns come full circle"
assert quarter_spin(TILE, 7) == [[3, 6], [2, 5], [1, 4]], "seven turns act like three"
assert quarter_spin([[1, 2], [3, 4]], 1) == [[3, 1], [4, 2]], "square grids still work"
assert quarter_spin([[9]], 5) == [[9]], "a single cell is unmoved"
print("ok")
