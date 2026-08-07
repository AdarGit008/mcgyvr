def expiry_cache(capacity: int, ops: list[list]) -> list[int]:
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        raise ValueError("capacity must be a positive integer")
    store: dict[str, tuple[int, int]] = {}
    results: list[int] = []
    last_time = None

    def clock(time):
        nonlocal last_time
        if last_time is not None and time < last_time:
            raise ValueError("time goes backwards")
        last_time = time
        return time

    for op in ops:
        kind = op[0]
        if kind == "set":
            _, time, key, value, ttl = op
            time = clock(time)
            if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl < 1:
                raise ValueError("ttl must be a positive integer")
            if key in store and store[key][1] > time:
                store[key] = (value, time + ttl)
                continue
            for dead in [k for k, (_, expiry) in store.items() if expiry <= time]:
                del store[dead]
            if len(store) >= capacity:
                victim = min(store, key=lambda k: (store[k][1], k))
                del store[victim]
            store[key] = (value, time + ttl)
        elif kind == "get":
            _, time, key = op
            time = clock(time)
            if key in store and store[key][1] > time:
                results.append(store[key][0])
            else:
                results.append(-1)
        else:
            raise ValueError(f"unknown operation {kind!r}")
    return results
