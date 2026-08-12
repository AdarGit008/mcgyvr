from solution import head_of

assert head_of(["a", "b", "c"], 2) == ["a", "b"], "the first two"
assert head_of(["a", "b"], 5) == ["a", "b"], "more than the list holds"
assert head_of(["a", "b"], 0) == [], "none asked for"
assert head_of([], 3) == [], "an empty list"
assert head_of(["a"], 1) == ["a"], "the only entry"
assert head_of(["p", "q", "r"], 1) == ["p"], "just the head"
print("ok")
