def merge_bookings(plan):
    if not isinstance(plan, str) or plan == "": raise ValueError("plan must be a non-empty string")
    slots = []
    for part in plan.split(","):
        ends = part.split("-")
        if len(ends) != 2 or not all(e.isdigit() for e in ends): raise ValueError("a slot reads start-end")
        start, end = int(ends[0]), int(ends[1])
        if start >= end or end > 24: raise ValueError("a slot must run forward inside the day")
        slots.append([start, end])
    merged = []
    for start, end in sorted(slots):
        if merged and start <= merged[-1][1]: merged[-1][1] = max(merged[-1][1], end)
        else: merged.append([start, end])
    return ",".join(f"{s}-{e}" for s, e in merged)
