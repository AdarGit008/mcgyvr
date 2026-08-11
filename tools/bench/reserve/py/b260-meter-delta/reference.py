def meter_delta(before: int, after: int, ceiling: int) -> int:
    if before >= ceiling or after >= ceiling:
        raise ValueError("reading is beyond the meter's ceiling")
    if after >= before:
        return after - before
    return ceiling - before + after
