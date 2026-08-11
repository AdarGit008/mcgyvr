from solution import overlap_any

assert overlap_any([[1, 5], [4, 8]]) is True, "the two run into each other"
assert overlap_any([[1, 4], [4, 8]]) is False, "touching is not overlapping"
assert overlap_any([[1, 2], [5, 6]]) is False, "well apart"
assert overlap_any([]) is False, "no bookings at all"
assert overlap_any([[1, 9]]) is False, "one booking cannot overlap"
assert overlap_any([[1, 2], [5, 6], [5, 7]]) is True, "the later pair overlaps"
print("ok")
