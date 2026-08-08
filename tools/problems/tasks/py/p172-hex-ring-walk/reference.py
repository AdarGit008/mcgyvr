STEPS = [
    [1, 0],
    [1, -1],
    [0, -1],
    [-1, 0],
    [-1, 1],
    [0, 1],
]

SOUTHWEST = 4


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def hex_ring_walk(center, radius):
    if not isinstance(center, list) or len(center) != 2:
        raise ValueError("the centre must be a two-element axial address")
    if not _whole(center[0]) or not _whole(center[1]):
        raise ValueError("axial coordinates must be whole numbers")
    if not _whole(radius):
        raise ValueError("the radius must be a whole number")
    if radius < 0:
        raise ValueError("the radius must not be negative")
    if radius == 0:
        return [[center[0], center[1]]]
    q = center[0] + STEPS[SOUTHWEST][0] * radius
    r = center[1] + STEPS[SOUTHWEST][1] * radius
    ring = []
    for step in STEPS:
        for _taken in range(radius):
            ring.append([q, r])
            q += step[0]
            r += step[1]
    return ring
