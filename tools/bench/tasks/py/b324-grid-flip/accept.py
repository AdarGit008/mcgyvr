from solution import grid_flip

assert grid_flip([[1, 2], [3, 4]]) == [[1, 3], [2, 4]], "a square turns"
assert grid_flip([[1, 2, 3]]) == [[1], [2], [3]], "one row becomes three"
assert grid_flip([[1], [2]]) == [[1, 2]], "one column becomes one row"
assert grid_flip([]) == [], "no rows at all"
assert grid_flip([[]]) == [], "a row holding nothing"
assert grid_flip([[1, 2], [3, 4], [5, 6]]) == [
    [1, 3, 5],
    [2, 4, 6],
], "three rows become two"
print("ok")
