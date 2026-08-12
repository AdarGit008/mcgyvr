from solution import stripe_rows

assert stripe_rows(2, ["red", "blue"]) == ["red", "blue"], "one pass"
assert stripe_rows(5, ["red", "blue"]) == [
    "red",
    "blue",
    "red",
    "blue",
    "red",
], "the list starts again"
assert stripe_rows(1, ["red", "blue", "green"]) == ["red"], "a short wall"
assert stripe_rows(0, ["red"]) == [], "no rows, no colours"
assert stripe_rows(3, ["grey"]) == ["grey", "grey", "grey"], "one colour repeats"
assert stripe_rows(4, ["a", "b", "c"]) == ["a", "b", "c", "a"], "wrapping mid-list"
print("ok")
