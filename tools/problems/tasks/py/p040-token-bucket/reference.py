def token_bucket(capacity: int, refill: int, requests: list[list[int]]) -> list[str]:
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        raise ValueError("capacity must be a positive integer")
    if not isinstance(refill, int) or isinstance(refill, bool) or refill < 0:
        raise ValueError("refill must be a non-negative integer")
    labels: list[str] = []
    tokens = capacity
    previous = 0
    for time, cost in requests:
        if not isinstance(time, int) or isinstance(time, bool) or time < 0:
            raise ValueError("arrival time must be a non-negative integer")
        if time < previous:
            raise ValueError("arrival times must never decrease")
        if not isinstance(cost, int) or isinstance(cost, bool) or cost < 1:
            raise ValueError("cost must be a positive integer")
        tokens = min(capacity, tokens + (time - previous) * refill)
        previous = time
        if tokens >= cost:
            tokens -= cost
            labels.append("grant")
        else:
            labels.append("refuse")
    return labels
