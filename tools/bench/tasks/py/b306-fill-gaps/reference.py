def is_gap(reading: int) -> bool:
    return reading == -1


def fill_gaps(readings: list) -> list:
    """Missing readings replaced by the last real one seen."""
    filled = []
    last = -1
    for reading in readings:
        if is_gap(reading):
            filled.append(last)
        else:
            filled.append(reading)
            last = reading
    return filled
