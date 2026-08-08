from solution import read_scanned_bars


def rejects(sweep):
    try:
        read_scanned_bars(sweep)
    except ValueError:
        return True
    return False


assert read_scanned_bars([2, 2, 4, 4, 2, 2, 2, 4, 2]) == {"digits": "0", "thin": 2}, (
    "the first two places fat name a zero"
)
assert read_scanned_bars([3, 3, 3, 3, 3, 6, 7, 9, 3]) == {"digits": "9", "thin": 3}, (
    "fat bars need not measure alike"
)
assert read_scanned_bars([1, 1, 2, 2, 1, 1, 1, 1, 1, 2, 2, 1, 2, 1]) == {
    "digits": "07",
    "thin": 1,
}, "two groups read as two digits"
assert read_scanned_bars([4, 4, 4, 8, 4, 8, 4, 8, 4]) == {"digits": "5", "thin": 4}, (
    "a coarse print reads the same way"
)
assert read_scanned_bars(
    [2, 2, 2, 5, 2, 5, 2, 2, 5, 2, 5, 2, 2, 5, 2, 5, 2, 5, 2]
) == {"digits": "555", "thin": 2}, "three groups read as three digits"
assert read_scanned_bars([1, 1, 1, 1, 2, 2, 1, 2, 1]) == {"digits": "7", "thin": 1}, (
    "the thin measure is the least reported anywhere"
)

assert rejects("2,2"), "the sweep must be a list"
assert rejects([1, 1, 1, 1, 1, 1, 1, 1]), "eight bars are too few"
assert rejects([2, 2, 4, 4, 2, 2, 0, 4, 2]), "a measure of zero is rejected"
assert rejects([2, 2, 4, 4, 2, 2, 2.5, 4, 2]), "a fractional measure is rejected"
assert rejects([2, 2, 3, 4, 2, 2, 2, 4, 2]), "a bar on the mark spoils the sweep"
assert rejects([2, 2, 7, 4, 2, 2, 2, 4, 2]), "too fat a bar spoils the sweep"
assert rejects([4, 2, 4, 4, 2, 2, 2, 4, 2]), "a fat opening mark is rejected"
assert rejects([2, 2, 4, 4, 2, 2, 2, 2, 2]), "a thin closing bar pair is rejected"
assert rejects([2, 2, 4, 4, 2, 2, 2, 2, 4, 2]), (
    "six bars between the marks do not divide by five"
)
assert rejects([2, 2, 4, 4, 4, 2, 2, 4, 2]), "three fat bars in a group are rejected"
assert rejects([2, 2, 4, 2, 2, 2, 2, 4, 2]), "one fat bar in a group is rejected"
print("ok")
