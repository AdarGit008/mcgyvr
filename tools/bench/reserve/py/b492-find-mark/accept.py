from solution import find_mark

assert find_mark([1, 3, 5, 7], 5) == 2, "a mark in the later half"
assert find_mark([1, 3, 5, 7], 1) == 0, "the opening mark"
assert find_mark([1, 3, 5, 7], 7) == 3, "the closing mark"
assert find_mark([2], 2) == 0, "a run of one holding the mark"
assert find_mark([1, 3, 5, 7], 4) == -1, "a mark the run does not hold"
assert find_mark([], 1) == -1, "a run holding nothing"
print("ok")
