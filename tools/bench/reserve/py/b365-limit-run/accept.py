from solution import over_limit, limit_run

assert over_limit(5, 3) is True, "five stands above three"
assert over_limit(3, 3) is False, "sitting on the limit is not over it"
assert limit_run([1, 2, 9, 1], 3) == [1, 2], "the run stops at the breach"
assert limit_run([9], 3) == [], "the opening reading is already over"
assert limit_run([], 3) == [], "no readings at all"
assert limit_run([1, 2], 3) == [1, 2], "nothing breaches the limit"
assert limit_run([3, 3], 3) == [3, 3], "readings on the limit are kept"
print("ok")
