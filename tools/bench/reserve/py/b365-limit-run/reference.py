def over_limit(reading: int, limit: int) -> bool:
    return reading > limit


def limit_run(readings: list, limit: int) -> list:
    kept = []
    for reading in readings:
        if over_limit(reading, limit):
            break
        kept.append(reading)
    return kept
