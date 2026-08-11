from solution import fold_ends

assert fold_ends([1, 2, 3, 4]) == [5, 5], "two pairs folded"
assert fold_ends([1, 2, 3]) == [4, 2], "the middle stands alone"
assert fold_ends([]) == [], "nothing to fold"
assert fold_ends([7]) == [7], "one entry is its own total"
assert fold_ends([1, 9]) == [10], "one pair"
assert fold_ends([1, 2, 3, 4, 5]) == [6, 6, 3], "five entries"
print("ok")
