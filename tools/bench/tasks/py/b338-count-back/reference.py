def count_back(start: int) -> list:
    """The numbers from a start down to one."""
    counted = []
    for value in range(start, 0, -1):
        counted.append(value)
    return counted
