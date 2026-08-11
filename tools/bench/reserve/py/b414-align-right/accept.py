from solution import widest_of, align_right

assert widest_of(["a", "bbb"]) == 3, "the longest entry"
assert widest_of([]) == 0, "no entries at all"
assert align_right(["1", "100"]) == ["  1", "100"], "aligned to the widest"
assert align_right([]) == [], "nothing to align"
assert align_right(["ab", "cd"]) == ["ab", "cd"], "already the same width"
assert align_right(["x"]) == ["x"], "one entry needs no spaces"
print("ok")
