from solution import top_three

assert top_three([5, 1, 9, 3]) == [9, 5, 3], "the highest three"
assert top_three([2, 2, 2, 2]) == [2, 2, 2], "all the same"
assert top_three([7, 4]) == [7, 4], "fewer than three"
assert top_three([3]) == [3], "one score"
assert top_three([]) == [], "no scores at all"
assert top_three([1, 2, 3, 4, 5]) == [5, 4, 3], "the tail is cut"
print("ok")
