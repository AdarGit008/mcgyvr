from solution import held_down, limit_map

assert held_down(9, 5) == 5, "brought down to the ceiling"
assert held_down(2, 5) == 2, "already under it"
assert limit_map({"a": 9, "b": 2}, 5) == {"a": 5, "b": 2}, "only the high one moves"
assert limit_map({}, 5) == {}, "an empty store"
assert limit_map({"a": 5}, 5) == {"a": 5}, "a value on the ceiling stays"
assert limit_map({"a": 9, "b": 8}, 5) == {"a": 5, "b": 5}, "everything comes down"
print("ok")
