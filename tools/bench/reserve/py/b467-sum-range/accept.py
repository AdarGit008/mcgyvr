from solution import sum_range

assert sum_range(1, 3) == 6, "one to three"
assert sum_range(5, 5) == 5, "the same number twice"
assert sum_range(4, 2) == 0, "the first stands above the second"
assert sum_range(0, 0) == 0, "nothing to nothing"
assert sum_range(1, 10) == 55, "one to ten"
assert sum_range(2, 3) == 5, "two to three"
print("ok")
