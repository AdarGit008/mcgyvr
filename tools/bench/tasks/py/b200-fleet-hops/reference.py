def fleet_hops(count: int, lts: list, builds: list, hop: int) -> int:
    """Total the hops a fleet makes climbing to the newest published release."""
    newest = count - 1
    total = 0
    for start in builds:
        if not isinstance(start, int) or not 0 <= start <= newest:
            raise ValueError("no such release")
        at = start
        while at < newest:
            landing = min(at + hop, newest)
            for stop in lts:
                if at < stop < landing:
                    landing = stop
            at = landing
            total += 1
    return total
