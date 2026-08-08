from solution import grade_tolerant_patches

assert grade_tolerant_patches([[4]], 0) == {
    "count": 1,
    "sizes": [1],
    "seeds": [0],
}, "a plate of one cell"
assert grade_tolerant_patches([[10, 10], [10, 10]], 0) == {
    "count": 1,
    "sizes": [4],
    "seeds": [0],
}, "one flat patch"
assert grade_tolerant_patches([[1, 3, 5]], 2) == {
    "count": 1,
    "sizes": [3],
    "seeds": [0],
}, "a slope holds together step by step"
assert grade_tolerant_patches([[1, 3, 5]], 1) == {
    "count": 3,
    "sizes": [1, 1, 1],
    "seeds": [0, 1, 2],
}, "too small a drift breaks every link"
assert grade_tolerant_patches([[0, 2, 4, 6]], 2) == {
    "count": 1,
    "sizes": [4],
    "seeds": [0],
}, "a longer slope still holds together"
assert grade_tolerant_patches([[1, 9], [9, 1]], 0) == {
    "count": 2,
    "sizes": [2, 2],
    "seeds": [0, 1],
}, "cells meeting only at a corner are linked"
assert grade_tolerant_patches([[5, 6, 20], [7, 8, 21]], 1) == {
    "count": 2,
    "sizes": [4, 2],
    "seeds": [0, 2],
}, "a corner step carries the chain across lines"
assert grade_tolerant_patches([[1, 1, 9], [1, 9, 9]], 0) == {
    "count": 2,
    "sizes": [3, 3],
    "seeds": [0, 2],
}, "patches of equal size go by earliest cell"


def rejects(plate, drift):
    try:
        grade_tolerant_patches(plate, drift)
    except ValueError:
        return True
    return False


assert rejects("plate", 0), "a non-list plate is rejected"
assert rejects([], 0), "a plate with no lines is rejected"
assert rejects([[]], 0), "a line with no cells is rejected"
assert rejects(["ab"], 0), "a line that is not a list is rejected"
assert rejects([[1], [1, 2]], 0), "lines of unequal length are rejected"
assert rejects([[1, None]], 0), "a non-number reading is rejected"
assert rejects([[1, 2]], -1), "a negative drift is rejected"
assert rejects([[1, 2]], 0.5), "a fractional drift is rejected"
print("ok")
