def min_gap(values: list) -> int:
    """The smallest difference between any two values."""
    if len(values) < 2:
        return -1
    ordered = sorted(values)
    smallest = ordered[1] - ordered[0]
    for i in range(1, len(ordered)):
        gap = ordered[i] - ordered[i - 1]
        if gap < smallest:
            smallest = gap
    return smallest
