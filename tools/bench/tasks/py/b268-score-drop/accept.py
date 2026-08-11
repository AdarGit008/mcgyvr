from solution import score_drop

assert score_drop([3, 1, 4]) == 7, "the lowest drops out"
assert score_drop([5, 5]) == 5, "one of a repeated lowest drops"
assert score_drop([2, 2, 2]) == 4, "only one copy drops"
assert score_drop([9]) == 0, "a single score totals nothing"
assert score_drop([]) == 0, "no scores, no total"
assert score_drop([10, 4, 4, 2]) == 18, "only the lowest goes"
print("ok")
