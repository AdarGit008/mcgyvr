from solution import window_max

assert window_max([1, 3, 2, 5], 2) == [3, 3, 5], "stretches of two"
assert window_max([1, 3, 2, 5], 3) == [3, 5], "stretches of three"
assert window_max([5, 5, 5], 2) == [5, 5], "readings that all match"
assert window_max([4], 1) == [4], "a stretch of one"
assert window_max([1, 2], 3) == [], "a run shorter than the width"
assert window_max([], 2) == [], "a run holding nothing"
print("ok")
