def ring_slot(capacity: int, writes: int, k: int) -> int:
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
        raise ValueError("capacity must be a positive integer")
    if isinstance(writes, bool) or not isinstance(writes, int) or writes < 0:
        raise ValueError("writes must be a non-negative integer")
    if isinstance(k, bool) or not isinstance(k, int) or k < 0:
        raise ValueError("k must be a non-negative integer")
    survivors = min(writes, capacity)
    if k >= survivors:
        raise ValueError("no survivor at that rank")
    return (writes - survivors + k) % capacity
