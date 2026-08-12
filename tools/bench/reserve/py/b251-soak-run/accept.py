from solution import soak_run

assert soak_run([1, 5, 6, 2, 7], 4) == 2, "the longest of two stretches"
assert soak_run([5, 5, 5], 4) == 3, "the whole run is wet"
assert soak_run([1, 2], 4) == 0, "never reaches the floor"
assert soak_run([], 4) == 0, "no readings at all"
assert soak_run([4, 4], 4) == 2, "sitting exactly on the floor counts"
assert soak_run([9, 1, 9, 9], 4) == 2, "a later stretch wins"
print("ok")
