from solution import skip_take

assert skip_take(["a", "b", "c", "d"], 1, 1) == ["a", "c"], "one on, one off"
assert skip_take(["a", "b", "c", "d", "e"], 2, 1) == [
    "a",
    "b",
    "d",
    "e",
], "two on, one off"
assert skip_take(["a", "b"], 5, 1) == ["a", "b"], "taking more than there is"
assert skip_take([], 1, 1) == [], "an empty list"
assert skip_take(["a", "b"], 0, 1) == [], "taking none"
assert skip_take(["a", "b", "c"], 3, 0) == ["a", "b", "c"], "taking everything"
print("ok")
