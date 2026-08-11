def pick_lane(queues, closed):
    if not isinstance(queues, list) or not queues:
        raise ValueError("pick_lane expects a non-empty list of queues")
    for length in queues:
        if isinstance(length, bool) or not isinstance(length, int) or length < 0:
            raise ValueError("queue lengths must be non-negative integers")
    for index in closed:
        if isinstance(index, bool) or not isinstance(index, int):
            raise ValueError("closed lane index out of range")
        if index < 0 or index >= len(queues):
            raise ValueError("closed lane index out of range")
    best = -1
    for lane, length in enumerate(queues):
        if lane in closed:
            continue
        if best == -1 or length < queues[best]:
            best = lane
    if best == -1:
        raise ValueError("every lane is closed")
    return best
