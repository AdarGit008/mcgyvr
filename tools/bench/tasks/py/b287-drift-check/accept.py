from solution import drift_check

assert drift_check([1, 2, 9], 3) == 2, "the jump is found"
assert drift_check([1, 2, 3], 3) == -1, "every step is small enough"
assert drift_check([5, 1], 3) == 1, "a fall drifts too"
assert drift_check([5], 1) == -1, "one reading cannot drift"
assert drift_check([], 1) == -1, "no readings at all"
assert drift_check([1, 4, 10, 2], 3) == 2, "a step on the allowance is fine"
print("ok")
