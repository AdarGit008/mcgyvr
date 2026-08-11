"""Walks a courier relay directory station by station."""


def trace_relay(links, start):
    for station, target in links.items():
        if station == "":
            raise ValueError("station names must be non-empty")
        if not isinstance(target, str):
            raise ValueError("every link must name a station or be empty")
    if not isinstance(start, str) or start not in links:
        raise ValueError("unknown starting station")
    path = []
    visited = set()
    current = start
    while True:
        if current in visited:
            raise ValueError("the relay circles back to " + current)
        visited.add(current)
        path.append(current)
        target = links[current]
        if target == "":
            return path
        if target not in links:
            raise ValueError("a link points at a station the directory does not hold")
        current = target
