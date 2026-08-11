from solution import dupe_keys

assert dupe_keys(["a", "b", "a"]) == ["a"], "one repeat"
assert dupe_keys(["a", "a", "a"]) == ["a"], "reported once however often"
assert dupe_keys(["a", "b", "c"]) == [], "no repeats at all"
assert dupe_keys([]) == [], "nothing in, nothing out"
assert dupe_keys(["b", "a", "b", "a"]) == ["b", "a"], "in order of first repeat"
assert dupe_keys(["x", "y", "y", "x"]) == ["y", "x"], "the inner pair repeats first"
print("ok")
