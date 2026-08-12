from solution import drop_outer

assert drop_outer(["a", "b", "c"]) == ["b"], "the middle survives"
assert drop_outer(["a", "b"]) == [], "two entries are both ends"
assert drop_outer(["a"]) == [], "one entry"
assert drop_outer([]) == [], "no entries at all"
assert drop_outer(["a", "b", "c", "d"]) == ["b", "c"], "two survive"
assert drop_outer(["w", "x", "y", "z", "0"]) == ["x", "y", "z"], "three survive"
print("ok")
