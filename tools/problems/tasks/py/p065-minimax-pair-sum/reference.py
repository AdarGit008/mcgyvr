def minimax_pair_sum(first, second):
    if not isinstance(first, list) or not isinstance(second, list):
        raise ValueError("expected two lists of integers")
    if not first or not second:
        raise ValueError("lists must be non-empty")
    if len(first) != len(second):
        raise ValueError("lists must have equal length")
    for values in (first, second):
        for value in values:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("entries must be integers")
    rising = sorted(first)
    falling = sorted(second, reverse=True)
    return max(a + b for a, b in zip(rising, falling))
