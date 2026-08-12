def kettle_hold(readings: list, target: int) -> int:
    held = 0
    for reading in reversed(readings):
        if reading < target:
            break
        held += 1
    return held
