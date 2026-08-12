"""Fewest links to ride between two stations of a transit map."""


def route_hops(links: list, origin: str, goal: str) -> int:
    if not all(isinstance(n, str) and n for n in (origin, goal)):
        raise ValueError("station names must be non-empty strings")
    next_stops = {}
    for link in links:
        if (not isinstance(link, list) or len(link) != 2
                or not all(isinstance(s, str) and s for s in link)):
            raise ValueError("a link must join two named stations")
        next_stops.setdefault(link[0], []).append(link[1])
        next_stops.setdefault(link[1], []).append(link[0])
    seen = {origin}
    queue = [(origin, 0)]
    for station, hops in queue:
        if station == goal:
            return hops
        for neighbour in next_stops.get(station, []):
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append((neighbour, hops + 1))
    return -1
