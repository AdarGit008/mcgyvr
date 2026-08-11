from solution import ramp_step, ramp_plan

assert ramp_step(0, 10, 3) == 3, "a full step toward the target"
assert ramp_step(9, 10, 3) == 10, "the last step never overshoots"
assert ramp_step(10, 0, 4) == 6, "stepping downward"
assert ramp_plan(0, 6, 2) == [0, 2, 4, 6], "an exact climb"
assert ramp_plan(0, 5, 2) == [0, 2, 4, 5], "a short final step"
assert ramp_plan(3, 3, 1) == [3], "already there"
assert ramp_plan(5, 2, 1) == [5, 4, 3, 2], "a descent"
print("ok")
