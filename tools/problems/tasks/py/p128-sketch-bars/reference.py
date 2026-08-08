def sketch_bars(readings: list[int], budget: int) -> list[str]:
    if not readings:
        raise ValueError("no values to sketch")
    if not isinstance(budget, int) or budget < 1:
        raise ValueError("budget must be a positive integer")
    for v in readings:
        if not isinstance(v, int) or v < 0:
            raise ValueError("values must be non-negative integers")
    top = max(readings)
    lines = []
    for v in readings:
        cells = 0
        if top > 0 and v > 0:
            cells = (2 * v * budget + top) // (2 * top)
            if cells == 0:
                cells = 1
        lines.append("#" * cells + "." * (budget - cells))
    return lines
