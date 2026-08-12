from solution import pick_nth

assert pick_nth(["a", "b", "c"], 1) == "a", "the first place"
assert pick_nth(["a", "b", "c"], 3) == "c", "the last place"
assert pick_nth(["a"], 0) == "", "there is no place nought"
assert pick_nth(["a"], 2) == "", "past the end of the list"
assert pick_nth([], 1) == "", "an empty list"
assert pick_nth(["x", "y"], 2) == "y", "the second place"
print("ok")
