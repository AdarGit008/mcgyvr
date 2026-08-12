def _check_rect(canvas, rect):
    if not isinstance(rect, list) or len(rect) != 4:
        raise ValueError("a rect is [top, left, bottom, right]")
    for bound in rect:
        if isinstance(bound, bool) or not isinstance(bound, int):
            raise ValueError("rect bounds must be integers")
    top, left, bottom, right = rect
    if top >= bottom or left >= right:
        raise ValueError("a rect must cover at least one cell")
    if top < 0 or left < 0 or bottom > canvas["rows"] or right > canvas["cols"]:
        raise ValueError("a rect must stay on the canvas")


def new_canvas(rows, cols):
    for side in (rows, cols):
        if isinstance(side, bool) or not isinstance(side, int) or side < 1:
            raise ValueError("canvas dimensions must be positive integers")
    cells = [[0] * cols for _ in range(rows)]
    return {"rows": rows, "cols": cols, "cells": cells}


def stamp_rect(canvas, rect):
    _check_rect(canvas, rect)
    top, left, bottom, right = rect
    inked = 0
    for r in range(top, bottom):
        for c in range(left, right):
            if canvas["cells"][r][c] == 0:
                canvas["cells"][r][c] = 1
                inked += 1
    return inked


def ink_total(canvas):
    total = 0
    for row in canvas["cells"]:
        total += sum(row)
    return total
