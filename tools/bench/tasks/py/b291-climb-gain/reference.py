def leg_gain(start: int, end: int) -> int:
    if end > start:
        return end - start
    return 0


def climb_gain(heights: list) -> int:
    total = 0
    for i in range(1, len(heights)):
        total += leg_gain(heights[i - 1], heights[i])
    return total
