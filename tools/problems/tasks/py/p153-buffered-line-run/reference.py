def run_buffered_line(capacities: list, buffers: list, ticks: int) -> dict:
    def pos_int(value):
        return isinstance(value, int) and not isinstance(value, bool) and value >= 1

    if not isinstance(capacities, list) or not capacities:
        raise ValueError("no stations")
    if not isinstance(buffers, list) or len(buffers) != len(capacities) - 1:
        raise ValueError("buffer count mismatch")
    for cap in capacities:
        if not pos_int(cap):
            raise ValueError("bad per-tick limit")
    for size in buffers:
        if not pos_int(size):
            raise ValueError("bad buffer size")
    if not isinstance(ticks, int) or isinstance(ticks, bool) or ticks < 0:
        raise ValueError("bad tick count")

    n = len(capacities)
    held = [0] * len(buffers)
    made = 0
    for _ in range(ticks):
        for i in range(n - 1, -1, -1):
            inbound = held[i - 1] if i > 0 else None
            room = buffers[i] - held[i] if i < n - 1 else None
            moved = capacities[i]
            if inbound is not None:
                moved = min(moved, inbound)
            if room is not None:
                moved = min(moved, room)
            if i > 0:
                held[i - 1] -= moved
            if i < n - 1:
                held[i] += moved
            else:
                made += moved
    return {"made": made, "left": held}
