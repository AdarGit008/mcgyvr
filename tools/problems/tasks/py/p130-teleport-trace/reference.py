def trace_teleports(pads: list[int], start: int) -> list[int]:
    n = len(pads)
    if n == 0:
        raise ValueError("empty hall")
    for p in pads:
        if not isinstance(p, int) or p < 0 or p >= n:
            raise ValueError("destination outside the hall")
    if not isinstance(start, int) or start < 0 or start >= n:
        raise ValueError("start outside the hall")
    seen_at = {}
    at = start
    rides = 0
    while at not in seen_at:
        seen_at[at] = rides
        at = pads[at]
        rides += 1
    entry = seen_at[at]
    return [entry, rides - entry, at]
