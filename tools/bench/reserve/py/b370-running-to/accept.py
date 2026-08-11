from solution import running_to

assert running_to([1, 2, 3], 1) == 3, "the named position is included"
assert running_to([1, 2, 3], 0) == 1, "the first position alone"
assert running_to([1, 2, 3], 9) == 6, "past the end totals everything"
assert running_to([1, 2, 3], -1) == 0, "below zero totals nothing"
assert running_to([], 0) == 0, "an empty list"
assert running_to([5], 0) == 5, "a single entry"
print("ok")
