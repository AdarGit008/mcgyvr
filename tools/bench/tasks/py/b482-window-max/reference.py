def window_max(readings: list[int], width: int) -> list[int]:
    out = []
    start = 0
    while start + width <= len(readings):
        best = readings[start]
        for step in range(1, width):
            if readings[start + step] > best:
                best = readings[start + step]
        out.append(best)
        start += 1
    return out
