from solution import grace_window

assert grace_window([100, 0, 100], 100, 1) == 3, "one grace day bridges the gap"
assert grace_window([100, 0, 100], 100, 0) == 1, "no grace, no bridge"
assert grace_window([100, 100, 0, 0, 100], 100, 1) == 2, "two misses exceed one grace day"
assert grace_window([100, 100, 0, 0, 100], 100, 2) == 5, "two grace days bridge both"
assert grace_window([0, 100, 0, 0, 0, 100, 0], 100, 3) == 5, (
    "the stretch must start and end on kept days"
)
assert grace_window([1, 2, 3], 10, 5) == 0, "no kept day means zero"
assert grace_window([5, 5, 5], 5, 0) == 3, "reaching the goal exactly keeps the day"
assert grace_window([7, 0, 7, 7, 0, 0, 7], 7, 1) == 4, (
    "grace is spent per stretch, not per gap"
)
assert grace_window([], 3, 2) == 0, "an empty log has no stretch"


def rejects(counts, goal, grace):
    try:
        grace_window(counts, goal, grace)
    except ValueError:
        return True
    return False


assert rejects([1], 0, 1), "a non-positive goal is rejected"
assert rejects([1], 5, -1), "negative grace is rejected"
print("ok")
