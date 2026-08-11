from solution import bin_spill, bin_add

assert bin_spill({"a": 5, "b": 2}, 3) == ["a"], "only the bin above the limit"
assert bin_spill({"a": 3}, 3) == [], "a bin exactly at the limit stays"
assert bin_spill({}, 1) == [], "no bins, nothing spills"
assert bin_spill({"a": 9, "b": 8}, 1) == ["a", "b"], "in the order added"
assert bin_add({}, "a", 2) == {"a": 2}, "a new bin takes the count"
assert bin_add({"a": 2}, "a", 3) == {"a": 5}, "an existing bin accumulates"
print("ok")
