from solution import change_pct

assert change_pct(10, 15) == 50, "half again as much"
assert change_pct(10, 5) == -50, "half as much"
assert change_pct(10, 10) == 0, "no change at all"
assert change_pct(0, 5) == 0, "nothing to change from"
assert change_pct(10, 0) == -100, "everything gone"
assert change_pct(10, 13) == 30, "a smaller rise"
print("ok")
