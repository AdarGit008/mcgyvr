from solution import fill_between

assert fill_between(["a", "b"], "-") == ["a", "-", "b"], "one filler"
assert fill_between(["a", "b", "c"], "-") == [
    "a",
    "-",
    "b",
    "-",
    "c",
], "three entries give five"
assert fill_between(["a"], "-") == ["a"], "one entry takes no filler"
assert fill_between([], "-") == [], "an empty list"
assert fill_between(["a", "b"], "") == ["a", "", "b"], "an empty filler"
assert fill_between(["x", "y", "z"], "|") == [
    "x",
    "|",
    "y",
    "|",
    "z",
], "another filler"
print("ok")
