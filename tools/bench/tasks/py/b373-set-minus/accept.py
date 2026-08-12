from solution import set_minus

assert set_minus(["a", "b", "c"], ["b"]) == ["a", "c"], "one entry removed"
assert set_minus(["a", "a"], ["b"]) == ["a", "a"], "repeats are kept"
assert set_minus(["a"], ["a"]) == [], "everything is removed"
assert set_minus([], ["a"]) == [], "nothing to remove from"
assert set_minus(["a", "b"], []) == ["a", "b"], "nothing to remove"
assert set_minus(["b", "a", "b"], ["a"]) == ["b", "b"], "order is kept"
print("ok")
