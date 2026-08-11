def stop_zone(stop: str) -> int:
    if stop == "central" or stop == "market":
        return 1
    if stop == "harbour":
        return 2
    return 3


def zone_fare(stops: list[str]) -> int:
    """Two hundred cents for every different zone the journey touches."""
    touched = set()
    for stop in stops:
        touched.add(stop_zone(stop))
    return len(touched) * 200
