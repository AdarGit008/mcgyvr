from solution import pad_mirrored_margins

RUN = [4, 7, 9]


def rejects(readings, left, right):
    try:
        pad_mirrored_margins(readings, left, right)
    except ValueError:
        return True
    return False


assert pad_mirrored_margins(RUN, 0, 0) == [4, 7, 9], "no margins leaves the run alone"
assert pad_mirrored_margins(RUN, 1, 0) == [
    4,
    4,
    7,
    9,
], "the first reading appears twice at the near glass"
assert pad_mirrored_margins(RUN, 0, 1) == [
    4,
    7,
    9,
    9,
], "the last reading appears twice at the far glass"
assert pad_mirrored_margins(RUN, 2, 2) == [7, 4, 4, 7, 9, 9, 7], "two on each side"
assert pad_mirrored_margins(RUN, 3, 3) == [
    9,
    7,
    4,
    4,
    7,
    9,
    9,
    7,
    4,
], "margins as long as the run itself"
assert pad_mirrored_margins(RUN, 7, 0) == [
    4,
    4,
    7,
    9,
    9,
    7,
    4,
    4,
    7,
    9,
], "a margin longer than the run bounces twice"
assert pad_mirrored_margins([5], 3, 2) == [
    5,
    5,
    5,
    5,
    5,
    5,
], "a run of one reading repeats forever"
assert pad_mirrored_margins([-2, 0, 5], 1, 1) == [
    -2,
    -2,
    0,
    5,
    5,
], "negative readings mirror like any other"
assert pad_mirrored_margins([0, 1], 1, 1) == [
    0,
    0,
    1,
    1,
], "a run of two reflects across both glasses"
assert pad_mirrored_margins([1, 2, 3, 4], 5, 5) == [
    4,
    4,
    3,
    2,
    1,
    1,
    2,
    3,
    4,
    4,
    3,
    2,
    1,
    1,
], "five each side of a run of four"

assert rejects([], 1, 1), "an empty run is rejected"
assert rejects("479", 1, 1), "a string is not a run"
assert rejects([4, 7.5], 1, 1), "a fractional reading is rejected"
assert rejects([4, "7"], 1, 1), "a lettered reading is rejected"
assert rejects(RUN, -1, 1), "a negative margin is rejected"
assert rejects(RUN, 1, 1.5), "a fractional margin is rejected"
assert rejects(RUN, None, 1), "a missing margin is rejected"
print("ok")
