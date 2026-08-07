from solution import smooth_with_taps

SERIES = [1, 2, 3, 4, 5]


def rejects(samples, taps):
    try:
        smooth_with_taps(samples, taps)
    except ValueError:
        return True
    return False


assert smooth_with_taps(SERIES, [1]) == [
    1,
    2,
    3,
    4,
    5,
], "a lone weight of one copies the series"
assert smooth_with_taps(SERIES, [0, 1, 0]) == [
    1,
    2,
    3,
    4,
    5,
], "a window that only reads its middle copies the series"
assert smooth_with_taps(SERIES, [1, 1, 1]) == [
    5,
    6,
    9,
    12,
    13,
], "a three-wide sum hinges at both ends"
assert smooth_with_taps(SERIES, [1, 0, -1]) == [
    0,
    -2,
    -2,
    -2,
    0,
], "a difference window flattens to nought at the hinges"
assert smooth_with_taps(SERIES, [1, 1, 1, 1, 1]) == [
    11,
    12,
    15,
    18,
    19,
], "a five-wide sum reaches two places past each end"
assert smooth_with_taps([7], [1, 1, 1]) == [
    21
], "a single sample swallows the whole window"
assert smooth_with_taps([1, 2], [1, 1, 1]) == [
    5,
    4,
], "a series of two alternates as it hinges"
assert smooth_with_taps([-1, 0, 1], [1, 1, 1]) == [
    -1,
    0,
    1,
], "negative samples hinge like any other"
assert smooth_with_taps([4, 4, 4], [2]) == [
    8,
    8,
    8,
], "a single weight scales every sample"

assert rejects([], [1]), "an empty series is rejected"
assert rejects("123", [1]), "a string is not a series"
assert rejects([1, 2.5], [1]), "a fractional sample is rejected"
assert rejects(SERIES, "1"), "a string is not a weight list"
assert rejects(SERIES, []), "an empty weight list is rejected"
assert rejects(SERIES, [1, 0.5, 1]), "a fractional weight is rejected"
assert rejects(SERIES, [1, 1]), "an even count of weights has no middle"
print("ok")
