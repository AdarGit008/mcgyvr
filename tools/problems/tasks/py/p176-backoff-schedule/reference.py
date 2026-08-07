def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def backoff_schedule(base, factor, cap, attempts):
    if not _whole(base) or base < 1:
        raise ValueError("base must be a whole number of one or more")
    if not _whole(factor) or factor < 1:
        raise ValueError("factor must be a whole number of one or more")
    if not _whole(cap) or cap < base:
        raise ValueError("cap must be a whole number no smaller than base")
    if not _whole(attempts) or attempts < 1:
        raise ValueError("attempts must be a whole number of one or more")
    moments = [0]
    idle = base
    clock = 0
    for _dial in range(1, attempts):
        waited = cap if idle > cap else idle
        clock += waited
        moments.append(clock)
        idle = cap if waited >= cap else idle * factor
    return moments
