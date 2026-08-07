def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _rungs(a: int, b: int) -> int:
    x, y = abs(a), abs(b)
    while y != 0:
        x, y = y, x % y
    return x


def hull_edge_stops(pegs: list) -> int:
    if not isinstance(pegs, list) or not pegs:
        raise ValueError("hull_edge_stops expects a non-empty list of pegs")
    points = []
    for peg in pegs:
        if (
            not isinstance(peg, list)
            or len(peg) != 2
            or not _whole(peg[0])
            or not _whole(peg[1])
        ):
            raise ValueError("a peg must be a pair of two whole numbers")
        if abs(peg[0]) > 1000000 or abs(peg[1]) > 1000000:
            raise ValueError("a coordinate magnitude passes one million")
        points.append([peg[0], peg[1]])
    points.sort()
    spots = []
    for point in points:
        if not spots or spots[-1] != point:
            spots.append(point)

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def chain_of(order):
        chain = []
        for point in order:
            while len(chain) >= 2 and turn(chain[-2], chain[-1], point) <= 0:
                chain.pop()
            chain.append(point)
        return chain

    if len(spots) == 1:
        posts = [spots[0]]
    else:
        posts = chain_of(spots)[:-1] + chain_of(list(reversed(spots)))[:-1]

    if len(posts) == 1:
        return 1
    if len(posts) == 2:
        return _rungs(posts[1][0] - posts[0][0], posts[1][1] - posts[0][1]) + 1
    stops = 0
    for index, here in enumerate(posts):
        following = posts[(index + 1) % len(posts)]
        stops += _rungs(following[0] - here[0], following[1] - here[1])
    return stops
