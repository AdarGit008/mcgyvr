from solution import min_gap

assert min_gap([1, 9, 2]) == 1, "the closest pair is not adjacent"
assert min_gap([5, 1]) == 4, "two values, one gap"
assert min_gap([3]) == -1, "one value has no gap"
assert min_gap([]) == -1, "no values at all"
assert min_gap([4, 4]) == 0, "two equal values are no distance apart"
assert min_gap([10, 1, 5, 2]) == 1, "order does not matter"
print("ok")
