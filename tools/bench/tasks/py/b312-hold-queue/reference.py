def hold_queue(callers: list, limit: int) -> list:
    if limit <= 0:
        raise ValueError("limit must be positive")
    waiting = []
    for caller in callers:
        waiting.append(caller)
        if len(waiting) > limit:
            waiting.pop(0)
    return waiting
