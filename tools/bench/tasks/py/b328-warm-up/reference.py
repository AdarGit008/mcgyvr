def warm_up(readings: list, floor: int) -> list:
    start = 0
    while start < len(readings) and readings[start] < floor:
        start += 1
    return readings[start:]
