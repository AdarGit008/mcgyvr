from solution import cycle_shape_report

assert cycle_shape_report([0]) == {
    "loops": [[0]],
    "widths": [1],
    "repeat": 1,
    "swing": "even",
}, "a single seat handing to itself"
assert cycle_shape_report([1, 0]) == {
    "loops": [[0, 1]],
    "widths": [2],
    "repeat": 2,
    "swing": "odd",
}, "one swap is odd"
assert cycle_shape_report([0, 1, 2, 3]) == {
    "loops": [[0], [1], [2], [3]],
    "widths": [1, 1, 1, 1],
    "repeat": 1,
    "swing": "even",
}, "every seat holds its own baton"
assert cycle_shape_report([1, 2, 0, 4, 3]) == {
    "loops": [[0, 1, 2], [3, 4]],
    "widths": [3, 2],
    "repeat": 6,
    "swing": "odd",
}, "a three-loop beside a two-loop"
assert cycle_shape_report([2, 3, 4, 5, 6, 7, 0, 1]) == {
    "loops": [[0, 2, 4, 6], [1, 3, 5, 7]],
    "widths": [4, 4],
    "repeat": 4,
    "swing": "even",
}, "two loops of equal width"
assert cycle_shape_report([3, 2, 1, 0]) == {
    "loops": [[0, 3], [1, 2]],
    "widths": [2, 2],
    "repeat": 2,
    "swing": "even",
}, "loops start at their lowest seat"
assert cycle_shape_report([1, 0, 3, 2, 5, 4]) == {
    "loops": [[0, 1], [2, 3], [4, 5]],
    "widths": [2, 2, 2],
    "repeat": 2,
    "swing": "odd",
}, "three swaps stay odd"
assert cycle_shape_report([1, 2, 3, 0, 5, 6, 7, 8, 9, 4]) == {
    "loops": [[0, 1, 2, 3], [4, 5, 6, 7, 8, 9]],
    "widths": [6, 4],
    "repeat": 12,
    "swing": "even",
}, "widths come biggest first and repeat is their least common multiple"


def rejects(value):
    try:
        cycle_shape_report(value)
    except ValueError:
        return True
    return False


assert rejects(42), "a non-list is rejected"
assert rejects([]), "an empty chart is rejected"
assert rejects([1.5, 0]), "a fractional entry is rejected"
assert rejects(["0", 1]), "a non-number entry is rejected"
assert rejects([1, 2]), "a seat outside the chart is rejected"
assert rejects([0, 0]), "a repeated seat is rejected"
print("ok")
