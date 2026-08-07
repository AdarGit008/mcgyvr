def level_strip(readings: list[int], low: int, high: int, ramp: str) -> str:
    if len(ramp) == 0:
        raise ValueError("empty ramp")
    if high <= low:
        raise ValueError("span must rise")
    n = len(ramp)
    out = []
    for r in readings:
        index = (r - low) * n // (high - low)
        if index < 0:
            index = 0
        if index >= n:
            index = n - 1
        out.append(ramp[index])
    return "".join(out)
