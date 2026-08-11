from solution import seat_run

assert seat_run("..x...", 3) == 3, "the run past the taken seat"
assert seat_run("..x...", 2) == 0, "the earliest run wins"
assert seat_run("xxx", 1) == -1, "the row is full"
assert seat_run("", 1) == -1, "there is no row"
assert seat_run("...", 3) == 0, "the whole row fits"
assert seat_run("x.x.x", 1) == 1, "a single seat between two taken"
print("ok")
