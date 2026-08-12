from solution import parcel_girth, parcel_oversize

assert parcel_girth(2, 3) == 10, "twice each side, added"
assert parcel_girth(0, 0) == 0, "a flat parcel has no girth"
assert parcel_oversize(10, 2, 3, 25) is False, "under the limit"
assert parcel_oversize(10, 2, 3, 15) is True, "over the limit"
assert parcel_oversize(5, 0, 0, 5) is False, "exactly at the limit is allowed"
assert parcel_oversize(6, 0, 0, 5) is True, "one unit past the limit"
print("ok")
