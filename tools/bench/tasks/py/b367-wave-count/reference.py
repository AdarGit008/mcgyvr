def wave_count(readings: list) -> int:
    changes = 0
    last = 0
    for i in range(1, len(readings)):
        way = 0
        if readings[i] > readings[i - 1]:
            way = 1
        elif readings[i] < readings[i - 1]:
            way = -1
        if way != 0 and last != 0 and way != last:
            changes += 1
        if way != 0:
            last = way
    return changes
