BOTTOM_CEILING = 10000000


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _greatest_common(a, b):
    left, right = abs(a), abs(b)
    while right != 0:
        left, right = right, left % right
    return left


def greedy_unit_parts(top: int, bottom: int) -> list:
    if not _whole(top) or not _whole(bottom):
        raise ValueError("top and bottom must be whole numbers")
    if bottom < 1 or bottom > 10000:
        raise ValueError("the bottom must lie in 1 through 10000")
    if top < 1:
        raise ValueError("the top must be above nothing")
    if top >= bottom:
        raise ValueError("the quotient must be below one")

    parts = []
    shrink = _greatest_common(top, bottom)
    rest_top, rest_bottom = top // shrink, bottom // shrink

    while rest_top != 0:
        if rest_bottom > BOTTOM_CEILING:
            raise ValueError("the remainder's bottom has exploded past the ceiling")
        piece = -((-rest_bottom) // rest_top)
        parts.append(piece)
        next_top = rest_top * piece - rest_bottom
        next_bottom = rest_bottom * piece
        if next_top == 0:
            break
        common = _greatest_common(next_top, next_bottom)
        rest_top, rest_bottom = next_top // common, next_bottom // common
    return parts
