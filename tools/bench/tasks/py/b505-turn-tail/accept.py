from solution import turn_tail

assert turn_tail(["a", "b", "c", "d"], 2) == ["a", "b", "d", "c"], "only the closing pair turns"
assert turn_tail(["a", "b", "c", "d"], 3) == ["a", "d", "c", "b"], "a longer closing stretch"
assert turn_tail(["a", "b", "c"], 3) == ["c", "b", "a"], "the whole run turns"
assert turn_tail(["a", "b", "c"], 5) == ["c", "b", "a"], "a count reaching past the run"
assert turn_tail(["a", "b", "c"], 0) == ["a", "b", "c"], "a count of nothing"
assert turn_tail([], 2) == [], "a run holding nothing"
print("ok")
