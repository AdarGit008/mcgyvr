from solution import slice_end, slice_plan

assert slice_end(0, 3, 10) == 3, "a slice well inside the total"
assert slice_end(8, 3, 10) == 10, "a slice held back by the total"
assert slice_plan(6, 3) == [[0, 3], [3, 6]], "two even slices"
assert slice_plan(7, 3) == [[0, 3], [3, 6], [6, 7]], "the last slice is short"
assert slice_plan(0, 3) == [], "nothing to cover"
assert slice_plan(2, 5) == [[0, 2]], "one slice covers it all"
print("ok")
