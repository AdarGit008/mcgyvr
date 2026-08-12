def run_total(readings: list, floor: int) -> list:
    """One total for each run of readings at or above a floor."""
    totals = []
    running = 0
    in_run = False
    for reading in readings:
        if reading >= floor:
            running += reading
            in_run = True
        elif in_run:
            totals.append(running)
            running = 0
            in_run = False
    if in_run:
        totals.append(running)
    return totals
