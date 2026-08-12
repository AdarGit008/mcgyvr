from solution import swap_ends

assert swap_ends(["a", "b", "c"]) == ["c", "b", "a"], "the ends trade places"
assert swap_ends(["a", "b"]) == ["b", "a"], "a pair is all ends"
assert swap_ends(["a"]) == ["a"], "one entry is unchanged"
assert swap_ends([]) == [], "an empty list"
assert swap_ends(["x", "y", "z", "w"]) == [
    "w",
    "y",
    "z",
    "x",
], "the middle stays put"

source = ["a", "b", "c"]
swap_ends(source)
assert source == ["a", "b", "c"], "the caller's list is left alone"
print("ok")
