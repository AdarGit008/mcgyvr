def route_stops(route: str) -> list:
    if not route.strip():
        return []
    return [stop.strip() for stop in route.split(">")]


def route_hops(route: str) -> int:
    stops = route_stops(route)
    return 0 if len(stops) == 0 else len(stops) - 1
