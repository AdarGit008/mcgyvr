def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def steady_readings(readings: object, spec: object) -> dict:
    if not isinstance(readings, list) or not readings:
        raise ValueError("the reading list must be a non-empty list")
    for reading in readings:
        if not _whole(reading):
            raise ValueError("a reading must be a whole number")
    if not isinstance(spec, dict):
        raise ValueError("the second argument must be a mapping")
    band = spec.get("band")
    hold = spec.get("hold")
    if not _whole(band) or band < 0:
        raise ValueError("band must be a non-negative whole number")
    if not _whole(hold) or hold < 1:
        raise ValueError("hold must be a positive whole number")

    steady = readings[0]
    opener = 0
    run = 0
    settled = [steady]
    moved = []
    for index in range(1, len(readings)):
        reading = readings[index]
        if abs(reading - steady) <= band:
            run = 0
        else:
            if run > 0 and abs(reading - opener) <= band:
                run += 1
            else:
                opener = reading
                run = 1
            if run >= hold:
                steady = opener
                run = 0
                moved.append(index)
        settled.append(steady)
    return {"settled": settled, "moved": moved}
