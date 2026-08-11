def lap_best(laps: list) -> int:
    best = 0
    for lap in laps:
        if lap > 0 and (best == 0 or lap < best):
            best = lap
    return best
