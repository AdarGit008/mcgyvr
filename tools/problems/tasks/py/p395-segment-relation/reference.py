def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _rod(given) -> list:
    if not isinstance(given, list) or len(given) != 2:
        raise ValueError("a rod must be a list of exactly two tips")
    tips = []
    for tip in given:
        if (
            not isinstance(tip, list)
            or len(tip) != 2
            or not _whole(tip[0])
            or not _whole(tip[1])
        ):
            raise ValueError("a tip must be a pair of two whole numbers")
        if abs(tip[0]) > 500 or abs(tip[1]) > 500:
            raise ValueError("a measure magnitude passes five hundred")
        tips.append([tip[0], tip[1]])
    if tips[0] == tips[1]:
        raise ValueError("a rod's tips coincide")
    return tips


def segment_relation(one: list, other: list) -> str:
    a, b = _rod(one)
    c, d = _rod(other)
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    qx, qy = c[0] - a[0], c[1] - a[1]
    twist = rx * sy - ry * sx
    if twist == 0:
        if qx * ry - qy * rx != 0:
            return "clear"
        mine = sorted([a, b])
        yours = sorted([c, d])
        low = max(mine[0], yours[0])
        high = min(mine[1], yours[1])
        if low > high:
            return "clear"
        return "pinned" if low == high else "shared"
    bottom = twist
    along = qx * sy - qy * sx
    across = qx * ry - qy * rx
    if bottom < 0:
        bottom, along, across = -bottom, -along, -across
    if along < 0 or along > bottom or across < 0 or across > bottom:
        return "clear"
    wide = a[0] * bottom + along * rx
    tall = a[1] * bottom + along * ry
    if wide % bottom == 0 and tall % bottom == 0:
        return "pinned"
    return "adrift"
