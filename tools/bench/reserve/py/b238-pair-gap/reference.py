def pair_gap(values: list) -> list:
    if len(values) < 2:
        raise ValueError("need at least two values")
    ordered = sorted(values)
    best = 0
    for i in range(1, len(ordered) - 1):
        if ordered[i + 1] - ordered[i] < ordered[best + 1] - ordered[best]:
            best = i
    return [ordered[best], ordered[best + 1]]
