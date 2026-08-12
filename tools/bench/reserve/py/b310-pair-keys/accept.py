from solution import pair_keys

assert pair_keys(["a", "b"], ["1", "2"]) == {"a": "1", "b": "2"}, "paired in order"
assert pair_keys(["a"], ["1", "2"]) == {"a": "1"}, "a spare code is left out"
assert pair_keys(["a", "b"], ["1"]) == {"a": "1"}, "a spare name is left out"
assert pair_keys([], []) == {}, "nothing to pair"
assert pair_keys(["a", "a"], ["1", "2"]) == {"a": "2"}, "the later code wins"
assert pair_keys(["x"], []) == {}, "no codes at all"
print("ok")
