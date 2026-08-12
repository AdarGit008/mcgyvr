from solution import baton_race

assert baton_race([10, 10], 2) == 22, "two legs pay one handover"
assert baton_race([1, 2, 3], 1) == 8, "three legs pay two handovers"
assert baton_race([7, 3], 5) == 15, "a costlier handover"
assert baton_race([5], 3) == 5, "a lone leg pays no handover"
assert baton_race([4, 4, 4, 4], 0) == 16, "a handover that costs nothing"
assert baton_race([], 4) == 0, "a race with no legs"
print("ok")
