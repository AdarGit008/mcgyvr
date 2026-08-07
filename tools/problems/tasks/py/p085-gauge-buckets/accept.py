from solution import gauge_buckets

assert gauge_buckets([0, 1, 2, 3, 4, 5], 0, 2, 2) == [
    0,
    2,
    2,
    2,
], "six pulses split two-two-two"
assert gauge_buckets([-3, -1, 0], 0, 2, 1) == [
    2,
    1,
    0,
], "pulses under the base are counted, never dropped"
assert gauge_buckets([5], 0, 5, 2) == [
    0,
    0,
    1,
    0,
], "a pulse on a shared edge belongs to the higher pocket"
assert gauge_buckets([6], 0, 10, 2) == [
    0,
    1,
    0,
    0,
], "position inside a pocket is found by its floor, not the nearest edge"
assert gauge_buckets([20, 47], 0, 10, 2) == [
    0,
    0,
    0,
    2,
], "a pulse at or past the top edge is overflow, not the last pocket"
assert gauge_buckets([-10, -1, 9, 10], -10, 5, 4) == [
    0,
    1,
    1,
    0,
    1,
    1,
], "a negative base shifts every pocket"
assert gauge_buckets([], 3, 4, 3) == [0, 0, 0, 0, 0], "no pulses, all zero"
print("ok")
