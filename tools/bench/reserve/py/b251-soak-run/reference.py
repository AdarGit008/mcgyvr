def soak_run(readings: list, floor: int) -> int:
    best = 0
    run = 0
    for reading in readings:
        run = run + 1 if reading >= floor else 0
        if run > best:
            best = run
    return best
