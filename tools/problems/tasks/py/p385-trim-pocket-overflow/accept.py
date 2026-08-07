from solution import trim_pocket_overflow

assert trim_pocket_overflow([300, 500, 200], 600) == [
    300,
    300,
    0,
], "the crossing entry is cut to the room left, not handed over whole"
assert trim_pocket_overflow([100, 100], 1000) == [
    100,
    100,
], "a ceiling nobody reaches changes nothing"
assert trim_pocket_overflow([100, 100], 0) == [0, 0], "a ceiling of zero hands over nothing"
assert trim_pocket_overflow([], 500) == [], "a year with no claims hands over nothing"
assert trim_pocket_overflow([700], 700) == [700], "an exact fit is handed over whole"
assert trim_pocket_overflow([700, 1], 700) == [700, 0], "the entry behind an exact fit is nothing"
assert trim_pocket_overflow([0, 0, 900], 400) == [
    0,
    0,
    400,
], "entries of zero leave the room untouched"
assert trim_pocket_overflow([250, 250, 250], 500) == [
    250,
    250,
    0,
], "two entries may land exactly on the ceiling"
assert trim_pocket_overflow([9000, 40, 5], 25) == [
    25,
    0,
    0,
], "the very first entry may be the crossing one"


def rejects(owed, ceiling):
    try:
        trim_pocket_overflow(owed, ceiling)
    except ValueError:
        return True
    return False


assert rejects([10], -1), "a negative ceiling is rejected"
assert rejects([10], 2.5), "a fractional ceiling is rejected"
assert rejects([10], "5"), "a non-numeric ceiling is rejected"
assert rejects([10, -1], 500), "a negative entry is rejected"
assert rejects([1.5], 500), "a fractional entry is rejected"
print("ok")
