def driest_window(rain, width):
    if not isinstance(rain, list):
        raise ValueError("rain must be a list of daily readings")
    if any(not isinstance(r, int) or r < 0 for r in rain):
        raise ValueError("every reading must be a non-negative integer")
    if not isinstance(width, int) or width < 1:
        raise ValueError("width must be a positive whole number")
    if width > len(rain):
        raise ValueError("width exceeds the number of days")
    totals = [sum(rain[s:s + width]) for s in range(len(rain) - width + 1)]
    return totals.index(min(totals))
