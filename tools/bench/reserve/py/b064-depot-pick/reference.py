"""Choose the depot a courier should ride to on the city grid."""


def taxi_distance(a: list, b: list) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def nearest_depot(origin: list, depots: list) -> int:
    if len(depots) == 0:
        raise ValueError("at least one depot is needed")
    for point in [origin] + depots:
        for value in point:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("coordinates must be integer blocks")
    best = 0
    best_distance = taxi_distance(origin, depots[0])
    for i in range(1, len(depots)):
        distance = taxi_distance(origin, depots[i])
        if distance < best_distance:
            best = i
            best_distance = distance
    return best
