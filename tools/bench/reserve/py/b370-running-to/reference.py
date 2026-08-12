def running_to(values: list, upto: int) -> int:
    """The total of the entries up to and including a position."""
    if upto < 0:
        return 0
    total = 0
    for value in values[: upto + 1]:
        total += value
    return total
