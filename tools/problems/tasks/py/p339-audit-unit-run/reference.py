RUNNING_CEILING = 1000000000


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _greatest_common(a, b):
    left, right = abs(a), abs(b)
    while right != 0:
        left, right = right, left % right
    return left


def audit_unit_run(top: int, bottom: int, parts: list) -> dict:
    if not _whole(top) or top < 0 or top > 100000:
        raise ValueError("the top must be a whole number from 0 through 100000")
    if not _whole(bottom) or bottom < 1 or bottom > 100000:
        raise ValueError("the bottom must be a whole number from 1 through 100000")
    if not isinstance(parts, list):
        raise ValueError("the run must be a list")
    if len(parts) > 10:
        raise ValueError("a run may hold at most ten pieces")
    earlier = 1
    for piece in parts:
        if not _whole(piece) or piece < 2 or piece > 100000:
            raise ValueError("a piece must be a whole number from 2 through 100000")
        if piece <= earlier:
            raise ValueError("the pieces must strictly rise")
        earlier = piece

    sum_top, sum_bottom = 0, 1
    for piece in parts:
        next_top = sum_top * piece + sum_bottom
        next_bottom = sum_bottom * piece
        common = _greatest_common(next_top, next_bottom)
        sum_top, sum_bottom = next_top // common, next_bottom // common
        if sum_bottom > RUNNING_CEILING:
            raise ValueError("the running total's bottom has passed the ceiling")

    gap_top = top * sum_bottom - sum_top * bottom
    if gap_top == 0:
        return {"verdict": "exact", "gap": [0, 1]}
    gap_bottom = bottom * sum_bottom
    common = _greatest_common(gap_top, gap_bottom)
    return {
        "verdict": "short" if gap_top > 0 else "over",
        "gap": [gap_top // common, gap_bottom // common],
    }
