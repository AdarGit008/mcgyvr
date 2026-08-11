def enter_count(states: list, wanted: str) -> int:
    entries = 0
    for i, state in enumerate(states):
        if state == wanted and (i == 0 or states[i - 1] != wanted):
            entries += 1
    return entries
