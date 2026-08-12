def run_elevator(top: int, calls: list) -> dict:
    if any(want < 1 or want > top for _, want in calls):
        raise ValueError("call floor outside the building")
    waiting = []
    stops = []
    floor = 1
    up = True
    travel = 0
    time = 0
    while len(stops) < len(calls):
        waiting.extend(want for tick, want in calls if tick == time)
        while floor in waiting:
            waiting.remove(floor)
            stops.append(floor)
        if waiting:
            if not any((want > floor) if up else (want < floor) for want in waiting):
                up = not up
            floor += 1 if up else -1
            travel += 1
        time += 1
    return {"stops": stops, "travel": travel}
