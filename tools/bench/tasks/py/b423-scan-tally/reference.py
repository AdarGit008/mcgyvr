def step_value(step: str) -> int:
    if step == "+":
        return 1
    if step == "-":
        return -1
    return 0


def scan_tally(steps: list) -> list:
    """The running total after each instruction."""
    running = []
    total = 0
    for step in steps:
        total += step_value(step)
        running.append(total)
    return running
