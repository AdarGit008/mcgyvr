from solution import ink_total, new_canvas, stamp_rect


def rejects(fn, *args):
    try:
        fn(*args)
    except Exception:
        return True
    return False


assert new_canvas(2, 3) == {
    "rows": 2,
    "cols": 3,
    "cells": [[0, 0, 0], [0, 0, 0]],
}, "a fresh canvas is blank"
canvas = new_canvas(2, 3)
assert stamp_rect(canvas, [0, 0, 1, 2]) == 2, "a stamp reports the cells it inked"
assert canvas["cells"] == [[1, 1, 0], [0, 0, 0]], "the stamp landed where aimed"
assert stamp_rect(canvas, [0, 1, 2, 3]) == 3, "an overlapping stamp counts only fresh cells"
assert canvas["cells"] == [[1, 1, 1], [0, 1, 1]], "overlap never double-marks"
assert ink_total(canvas) == 5, "the total counts every inked cell"
assert stamp_rect(canvas, [0, 0, 2, 3]) == 1, "a covering stamp finds the last blank cell"
assert stamp_rect(canvas, [0, 0, 2, 3]) == 0, "a stamp over solid ink counts nothing"
assert rejects(new_canvas, 0, 3), "zero rows are rejected"
assert rejects(new_canvas, 2, 2.5), "fractional columns are rejected"
assert rejects(stamp_rect, canvas, [1, 0, 1, 3]), "an empty rect is rejected"
assert rejects(stamp_rect, canvas, [0, 0, 3, 3]), "a rect off the canvas is rejected"
assert rejects(stamp_rect, canvas, [0, 0, 1]), "a three-bound rect is rejected"
assert rejects(stamp_rect, canvas, [-1, 0, 1, 1]), "a negative top is rejected"
print("ok")
