from solution import cross_up

assert cross_up([1, 5], 3) == 1, "one crossing upward"
assert cross_up([5, 1], 3) == 0, "a fall is not a crossing"
assert cross_up([1, 5, 1, 5], 3) == 2, "two crossings"
assert cross_up([], 3) == 0, "no readings at all"
assert cross_up([3, 3], 3) == 0, "sitting on the level is not crossing it"
assert cross_up([1, 3], 3) == 1, "reaching the level counts"
print("ok")
