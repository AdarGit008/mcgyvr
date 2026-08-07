def apply_cycle_power(panel: list[int], rounds: int) -> list[int]:
    if not isinstance(panel, list) or not panel:
        raise ValueError("the panel must be a non-empty list")
    if not isinstance(rounds, int) or isinstance(rounds, bool) or rounds < 0:
        raise ValueError("rounds must be a whole number of zero or more")
    size = len(panel)
    named = set()
    for entry in panel:
        if not isinstance(entry, int) or isinstance(entry, bool):
            raise ValueError("every entry must be a whole number")
        if entry < 0 or entry >= size:
            raise ValueError("entry names a slot the panel does not have")
        if entry in named:
            raise ValueError("a slot is named twice")
        named.add(entry)
    settled = [False] * size
    moved = [0] * size
    for start in range(size):
        if settled[start]:
            continue
        ring = []
        at = start
        while not settled[at]:
            settled[at] = True
            ring.append(at)
            at = panel[at]
        slide = rounds % len(ring)
        for i in range(len(ring)):
            moved[ring[i]] = ring[(i + slide) % len(ring)]
    return moved
