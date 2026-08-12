from solution import warm_up

assert warm_up([1, 2, 5, 1], 3) == [5, 1], "the warm-up is dropped"
assert warm_up([5, 1], 3) == [5, 1], "there was no warm-up"
assert warm_up([1, 1], 3) == [], "the floor is never reached"
assert warm_up([], 3) == [], "no readings at all"
assert warm_up([3], 3) == [3], "a reading on the floor counts"
assert warm_up([1, 4, 1, 4], 4) == [4, 1, 4], "only the opening is dropped"
print("ok")
