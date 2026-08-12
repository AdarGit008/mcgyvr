from solution import quota_share

assert quota_share(10, [1, 1]) == [5, 5], "an even split"
assert quota_share(10, [3, 1]) == [8, 2], "the leftover follows the weight"
assert quota_share(7, [1, 1, 1]) == [3, 2, 2], "one unit left over"
assert quota_share(5, [0, 0]) == [0, 0], "no weight, no claim"
assert quota_share(0, [1, 2]) == [0, 0], "nothing to hand out"
assert quota_share(9, [2, 1]) == [6, 3], "an exact proportion"
print("ok")
