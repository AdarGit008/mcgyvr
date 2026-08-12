from solution import half_life

assert half_life(100, 1) == 50, "one clean halving"
assert half_life(7, 1) == 3, "the fraction is discarded"
assert half_life(7, 2) == 1, "and again"
assert half_life(100, 0) == 100, "no steps, no change"
assert half_life(0, 5) == 0, "nothing halves to nothing"
assert half_life(1, 3) == 0, "one falls to nothing and stays"
print("ok")
