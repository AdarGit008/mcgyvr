def tide_marks(levels: list) -> list:
    peaks = []
    for i in range(1, len(levels) - 1):
        if levels[i] > levels[i - 1] and levels[i] > levels[i + 1]:
            peaks.append(i)
    return peaks
