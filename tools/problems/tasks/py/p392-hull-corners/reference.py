def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def hull_corners(markers: list) -> list:
    if not isinstance(markers, list) or not markers:
        raise ValueError("hull_corners expects a non-empty list of markers")
    points = []
    for marker in markers:
        if (
            not isinstance(marker, list)
            or len(marker) != 2
            or not _whole(marker[0])
            or not _whole(marker[1])
        ):
            raise ValueError("a marker must be a pair of two whole numbers")
        if abs(marker[0]) > 1000000 or abs(marker[1]) > 1000000:
            raise ValueError("a coordinate magnitude passes one million")
        points.append([marker[0], marker[1]])
    points.sort()
    spots = []
    for point in points:
        if not spots or spots[-1] != point:
            spots.append(point)
    if len(spots) == 1:
        return [spots[0]]

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def chain_of(order):
        chain = []
        for point in order:
            while len(chain) >= 2 and turn(chain[-2], chain[-1], point) <= 0:
                chain.pop()
            chain.append(point)
        return chain

    lower = chain_of(spots)
    upper = chain_of(list(reversed(spots)))
    return lower[:-1] + upper[:-1]
