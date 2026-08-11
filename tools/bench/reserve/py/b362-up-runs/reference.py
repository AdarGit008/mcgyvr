def up_runs(readings: list) -> int:
    best = 0
    run = 0
    for i in range(len(readings)):
        if i > 0 and readings[i] > readings[i - 1]:
            run += 1
        else:
            run = 1
        if run > best:
            best = run
    return best
