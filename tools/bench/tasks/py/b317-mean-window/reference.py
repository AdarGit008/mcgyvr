def mean_window(readings: list, size: int) -> list:
    means = []
    for i in range(len(readings) - size + 1):
        window = readings[i : i + size]
        means.append(sum(window) // size)
    return means
