from solution import interest_add

assert interest_add(1000, 5, 2) == 1100, "two years at five percent"
assert interest_add(1000, 5, 0) == 1000, "no years, no interest"
assert interest_add(100, 3, 1) == 103, "one year at three percent"
assert interest_add(0, 10, 5) == 0, "nothing earns nothing"
assert interest_add(999, 1, 1) == 1008, "the interest is rounded down"
assert interest_add(200, 50, 1) == 300, "half again in a year"
print("ok")
