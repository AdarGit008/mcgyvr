WEIGHT_LIMIT = 10000


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _band(width, what):
    if not _whole(width) or width < 1 or width > 1000:
        raise ValueError(f"{what} must be a whole number between 1 and 1000")


def _read_bag(bag, head, tail):
    if not isinstance(bag, list):
        raise ValueError("a bag must be a list")
    seen = set()
    links = []
    for link in bag:
        if not isinstance(link, (list, tuple)) or len(link) != 3:
            raise ValueError("every link must be a triple")
        start, end, weight = link[0], link[1], link[2]
        if not _whole(start) or start < 0 or start >= head:
            raise ValueError("an endpoint lies outside its band")
        if not _whole(end) or end < 0 or end >= tail:
            raise ValueError("an endpoint lies outside its band")
        if not _whole(weight) or abs(weight) > WEIGHT_LIMIT:
            raise ValueError("a weight must be a whole number within the size limit")
        if weight == 0:
            raise ValueError("a bag may not store a weight of nothing")
        if (start, end) in seen:
            raise ValueError("a bag holds two links between the same endpoints")
        seen.add((start, end))
        links.append((start, end, weight))
    return links


def triplet_chain_cells(
    first: list, second: list, lefts: int, mids: int, rights: int
) -> list:
    _band(lefts, "lefts")
    _band(mids, "mids")
    _band(rights, "rights")

    ones = _read_bag(first, lefts, mids)
    twos = _read_bag(second, mids, rights)

    leaving = {}
    for middle, sink, gain in twos:
        leaving.setdefault(middle, []).append((sink, gain))

    routes = {}
    for source, middle, weight in ones:
        for sink, gain in leaving.get(middle, ()):
            pair = (source, sink)
            routes[pair] = routes.get(pair, 0) + weight * gain

    out = [
        [source, sink, weight]
        for (source, sink), weight in routes.items()
        if weight != 0
    ]
    out.sort(key=lambda route: (route[0], route[1]))
    return out
