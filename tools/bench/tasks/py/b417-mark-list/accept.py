from solution import mark_list

assert mark_list([1, 5], 3) == ["1", "5*"], "only the high one is marked"
assert mark_list([3], 3) == ["3*"], "reaching the floor counts"
assert mark_list([1], 3) == ["1"], "below the floor is unmarked"
assert mark_list([], 3) == [], "nothing to mark"
assert mark_list([5, 6], 3) == ["5*", "6*"], "everything is marked"
assert mark_list([1, 2], 3) == ["1", "2"], "nothing is marked"
print("ok")
