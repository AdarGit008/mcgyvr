def step_allowed(start: str, end: str, allowed: list) -> bool:
    for move in allowed:
        if move[0] == start and move[1] == end:
            return True
    return False


def step_plan(states: list, allowed: list) -> int:
    if not states:
        raise ValueError("a run needs at least one state")
    for i in range(1, len(states)):
        if not step_allowed(states[i - 1], states[i], allowed):
            return i
    return -1
