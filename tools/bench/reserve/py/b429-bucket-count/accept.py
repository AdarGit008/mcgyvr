from solution import bucket_count

assert bucket_count([1, 2, 11], 10) == {0: 2, 10: 1}, "two buckets"
assert bucket_count([0], 10) == {0: 1}, "the lowest bucket"
assert bucket_count([], 10) == {}, "no readings at all"
assert bucket_count([10, 19], 10) == {10: 2}, "one bucket holds both"
assert bucket_count([5], 5) == {5: 1}, "a reading on a boundary goes up"
assert bucket_count([1, 1, 1], 10) == {0: 3}, "three in one bucket"
print("ok")
