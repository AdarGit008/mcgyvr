def cross_up(readings: list, level: int) -> int:
    crossings = 0
    for i in range(1, len(readings)):
        if readings[i - 1] < level and readings[i] >= level:
            crossings += 1
    return crossings
