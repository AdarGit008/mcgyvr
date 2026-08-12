def mid_pair(values: list) -> list:
    if not values:
        return [0, 0]
    ordered = sorted(values)
    half = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return [ordered[half], ordered[half]]
    return [ordered[half - 1], ordered[half]]
