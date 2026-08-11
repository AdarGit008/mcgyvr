from solution import step_cost, trip_cost

assert step_cost(10, 3) == 30, "distance times rate"
assert step_cost(0, 3) == 0, "no distance, no cost"
assert trip_cost([10, 10], 3, 50) == 60, "the hops add up past the minimum"
assert trip_cost([1, 1], 3, 50) == 50, "a cheap trip pays the minimum once"
assert trip_cost([], 3, 50) == 50, "an empty trip still pays it"
assert trip_cost([100], 3, 50) == 300, "one long hop"
print("ok")
