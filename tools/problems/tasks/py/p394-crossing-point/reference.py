def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _read(stroke) -> list:
    if not isinstance(stroke, list) or len(stroke) != 2:
        raise ValueError("a stroke must be a list of exactly two ends")
    ends = []
    for end in stroke:
        if (
            not isinstance(end, list)
            or len(end) != 2
            or not _whole(end[0])
            or not _whole(end[1])
        ):
            raise ValueError("an end must be a pair of two whole numbers")
        if abs(end[0]) > 1000 or abs(end[1]) > 1000:
            raise ValueError("a coordinate magnitude passes one thousand")
        ends.append([end[0], end[1]])
    if ends[0] == ends[1]:
        raise ValueError("a stroke's two ends sit on the same spot")
    return ends


def _reduce(top: int, bottom: int) -> list:
    x, y = abs(top), bottom
    while y != 0:
        x, y = y, x % y
    step = x if x != 0 else 1
    return [top // step, bottom // step]


def crossing_point(first: list, second: list) -> dict:
    a, b = _read(first)
    c, d = _read(second)
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    qx, qy = c[0] - a[0], c[1] - a[1]
    denom = rx * sy - ry * sx
    if denom == 0:
        if qx * ry - qy * rx != 0:
            return {"kind": "apart"}
        mine = sorted([a, b])
        yours = sorted([c, d])
        low = max(mine[0], yours[0])
        high = min(mine[1], yours[1])
        if low > high:
            return {"kind": "apart"}
        if low == high:
            return {"kind": "point", "x": [low[0], 1], "y": [low[1], 1]}
        return {"kind": "stretch", "from": low, "to": high}
    bottom = denom
    along = qx * sy - qy * sx
    across = qx * ry - qy * rx
    if bottom < 0:
        bottom, along, across = -bottom, -along, -across
    if along < 0 or along > bottom or across < 0 or across > bottom:
        return {"kind": "apart"}
    return {
        "kind": "point",
        "x": _reduce(a[0] * bottom + along * rx, bottom),
        "y": _reduce(a[1] * bottom + along * ry, bottom),
    }
