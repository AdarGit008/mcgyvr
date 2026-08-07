def pad_mirrored_margins(readings: list[int], left: int, right: int) -> list[int]:
    if not isinstance(readings, list) or not readings:
        raise ValueError("the run must be a non-empty list")
    for reading in readings:
        if isinstance(reading, bool) or not isinstance(reading, int):
            raise ValueError("every reading is a whole number")
    for width in (left, right):
        if isinstance(width, bool) or not isinstance(width, int) or width < 0:
            raise ValueError("a margin width is a whole number at or above nought")

    span = len(readings)
    period = span * 2

    def at(index: int) -> int:
        folded = index % period
        if folded >= span:
            folded = period - 1 - folded
        return readings[folded]

    return [at(index) for index in range(-left, span + right)]
