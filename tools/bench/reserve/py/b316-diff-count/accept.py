from solution import diff_count

assert diff_count([1, 2, 3], [1, 9, 3]) == 1, "one position differs"
assert diff_count([1, 2], [1, 2]) == 0, "the same list twice"
assert diff_count([1, 2, 3], [1, 2]) == 1, "an extra position counts"
assert diff_count([], []) == 0, "two empty lists"
assert diff_count([], [1, 2]) == 2, "every position is extra"
assert diff_count([1, 2], [3, 4]) == 2, "nothing matches"
print("ok")
