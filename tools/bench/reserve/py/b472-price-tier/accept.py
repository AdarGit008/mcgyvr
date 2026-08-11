from solution import tier_cost

assert tier_cost(0) == 0, "a count of nothing costs nothing"
assert tier_cost(1) == 100, "a small charge is lifted to the floor"
assert tier_cost(2) == 100, "still under the floor"
assert tier_cost(4) == 200, "above the floor at the first rate"
assert tier_cost(10) == 400, "the rate steps down"
assert tier_cost(50) == 1500, "the rate steps down again"
print("ok")
