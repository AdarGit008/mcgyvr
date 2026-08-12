from solution import stride_skip, stride_take, stride_weave

assert stride_weave([]) == [], "no parts weave to an empty list"
assert stride_weave([[1, 2, 3]]) == [1, 2, 3], "one part is itself"
assert stride_weave([[1, 3], [2, 4]]) == [1, 2, 3, 4], "equal parts"
assert stride_weave([[1, 4, 6], [2, 5], [3]]) == [
    1,
    2,
    3,
    4,
    5,
    6,
], "uneven tails are passed over"
assert stride_weave([[1, 3], [], [2, 4]]) == [
    1,
    2,
    3,
    4,
], "an empty part never contributes"
whole = [10, 11, 12, 13, 14, 15, 16]
assert (
    stride_weave(
        [
            stride_take(whole, 3, 0),
            stride_take(whole, 3, 1),
            stride_take(whole, 3, 2),
        ]
    )
    == whole
), "weaving the strides rebuilds the list"
assert stride_weave([[7, 9], [7]]) == [7, 7, 9], "duplicates keep order"


def rejects(fn, *args):
    try:
        fn(*args)
    except Exception:
        return True
    return False


assert rejects(stride_weave, 42), "parts must be a list"
assert rejects(stride_weave, [[1], 5]), "every part must be a list"
assert stride_take([10, 11, 12, 13, 14], 2, 0) == [10, 12, 14], "take offset 0"
assert stride_take([10, 11, 12, 13, 14], 2, 1) == [11, 13], "take offset 1"
assert rejects(stride_take, [1, 2], 0, 0), "zero step is rejected"
assert stride_skip([10, 11, 12, 13, 14], 2, 0) == [11, 13], "skip is the complement"
assert rejects(stride_skip, [1, 2], 2, 2), "offset must sit below step"
print("ok")
