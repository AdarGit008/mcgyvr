"""A deterministic irrigation reservoir: fill, spill, then draw, per tick."""


def run_reservoir(capacity, start, ticks):
    """Return {level, spilled, shortfall, served} after the final tick."""
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
        raise ValueError("capacity must be a positive integer")
    if isinstance(start, bool) or not isinstance(start, int):
        raise ValueError("start level must be an integer")
    if start < 0 or start > capacity:
        raise ValueError("start level must lie within the capacity")
    level = start
    spilled = 0
    shortfall = 0
    served = 0
    for tick in ticks:
        if not isinstance(tick, list) or len(tick) != 2:
            raise ValueError("each tick is an [inflow, demand] pair")
        inflow, demand = tick
        if isinstance(inflow, bool) or not isinstance(inflow, int) or inflow < 0:
            raise ValueError("inflow must be a non-negative integer")
        if isinstance(demand, bool) or not isinstance(demand, int) or demand < 0:
            raise ValueError("demand must be a non-negative integer")
        level += inflow
        if level > capacity:
            spilled += level - capacity
            level = capacity
        drawn = min(level, demand)
        served += drawn
        shortfall += demand - drawn
        level -= drawn
    return {
        "level": level,
        "spilled": spilled,
        "shortfall": shortfall,
        "served": served,
    }
