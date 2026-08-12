def mark_value(mark: str) -> int:
    if mark == "a":
        return 1
    if mark == "b":
        return 2
    if mark == "c":
        return 3
    return 0


def tally_marks(line: str) -> int:
    """A line of marks totalled, doubling a mark that follows its own kind."""
    total = 0
    previous = ""
    for mark in line:
        worth = mark_value(mark)
        if mark == previous:
            total += worth * 2
        else:
            total += worth
        previous = mark
    return total
