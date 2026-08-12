def range_check(readings: list, low: int, high: int) -> bool:
    if low > high:
        raise ValueError("the low must not stand above the high")
    for reading in readings:
        if reading < low or reading > high:
            return False
    return True
