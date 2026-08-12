from solution import split_at

assert split_at(["a", "x", "b"], "x") == [["a"], ["b"]], "broken at the marker"
assert split_at(["a"], "x") == [["a"], []], "the marker is absent"
assert split_at([], "x") == [[], []], "an empty list"
assert split_at(["x"], "x") == [[], []], "the marker is all there is"
assert split_at(["x", "a"], "x") == [[], ["a"]], "the marker leads"
assert split_at(["a", "x", "b", "x"], "x") == [
    ["a"],
    ["b", "x"],
], "only the first marker breaks it"
print("ok")
