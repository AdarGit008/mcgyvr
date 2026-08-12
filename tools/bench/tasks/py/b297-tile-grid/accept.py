from solution import tiles_across, tiles_needed

assert tiles_across(100, 10) == 10, "an exact fit"
assert tiles_across(101, 10) == 11, "a part tile counts as one"
assert tiles_across(0, 10) == 0, "no length, no tiles"
assert tiles_needed(100, 100, 10, 0) == 100, "no allowance"
assert tiles_needed(100, 100, 10, 5) == 105, "an exact allowance"
assert tiles_needed(30, 20, 10, 10) == 7, "the allowance rounds up"
assert tiles_needed(0, 50, 10, 10) == 0, "no wall, no tiles"
print("ok")
