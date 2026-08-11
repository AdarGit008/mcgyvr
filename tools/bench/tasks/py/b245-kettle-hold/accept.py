from solution import kettle_hold

assert kettle_hold([90, 95, 96], 95) == 2, "the tail that held"
assert kettle_hold([96, 96], 95) == 2, "the whole run held"
assert kettle_hold([90], 95) == 0, "never reached the target"
assert kettle_hold([], 95) == 0, "no readings at all"
assert kettle_hold([95, 90, 95], 95) == 1, "an earlier dip does not count"
assert kettle_hold([100, 100, 100], 50) == 3, "well above throughout"
print("ok")
