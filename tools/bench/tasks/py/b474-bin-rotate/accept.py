from solution import bin_rotate

assert bin_rotate(["a", "b", "c", "d"], 1) == ["d", "a", "b", "c"], "one place forward"
assert bin_rotate(["a", "b", "c", "d"], 2) == ["c", "d", "a", "b"], "two places forward"
assert bin_rotate(["a", "b"], 1) == ["b", "a"], "a run of two"
assert bin_rotate(["a", "b", "c"], 0) == ["a", "b", "c"], "a move of nothing"
assert bin_rotate(["a", "b", "c"], 3) == ["a", "b", "c"], "a move as long as the run"
assert bin_rotate([], 2) == [], "an empty run"
print("ok")
