from solution import pair_sums

assert pair_sums([1, 2, 3]) == [3, 5], "three readings, two pairs"
assert pair_sums([1, 2]) == [3], "one pair"
assert pair_sums([5]) == [], "one reading holds no pair"
assert pair_sums([]) == [], "no readings at all"
assert pair_sums([0, 0, 0]) == [0, 0], "nothing adds to nothing"
assert pair_sums([1, -1, 2]) == [0, 1], "a pair may cancel out"
print("ok")
