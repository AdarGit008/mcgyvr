from solution import in_both, shared_of

assert in_both("a", ["a"], ["a"]) is True, "held by both"
assert in_both("a", ["a"], ["b"]) is False, "held by one only"
assert shared_of(["a", "b"], ["b", "c"]) == ["b"], "one entry is shared"
assert shared_of(["a"], ["b"]) == [], "nothing is shared"
assert shared_of([], ["a"]) == [], "an empty first list"
assert shared_of(["a", "a"], ["a"]) == ["a"], "a repeat is reported once"
print("ok")
