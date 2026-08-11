from solution import part_ways

assert part_ways(["a", "b", "c"], ["a", "x", "c"]) == 1, "they part in the middle"
assert part_ways(["x"], ["y"]) == 0, "they part at the opening"
assert part_ways(["a", "b"], ["a", "b", "c"]) == 2, "one run carries on"
assert part_ways(["a", "b", "c"], ["a", "b"]) == 2, "the longer run may come first"
assert part_ways(["a"], ["a"]) == -1, "the two runs agree"
assert part_ways([], []) == -1, "two runs holding nothing agree"
assert part_ways([], ["a"]) == 0, "one run holds nothing"
print("ok")
