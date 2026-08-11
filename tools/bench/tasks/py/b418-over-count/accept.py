from solution import over_count

assert over_count({"a": 1, "b": 5}, 3) == 1, "only the high one counts"
assert over_count({"a": 3}, 3) == 1, "reaching the floor counts"
assert over_count({"a": 1}, 3) == 0, "below the floor does not"
assert over_count({}, 3) == 0, "an empty store"
assert over_count({"a": 5, "b": 6}, 3) == 2, "everything counts"
assert over_count({"a": 1, "b": 2}, 3) == 0, "nothing counts"
print("ok")
