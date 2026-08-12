"""The cheapest set of travel passes covering every trip day."""


def _validate_plan(trip_days, passes):
    for day in trip_days:
        if isinstance(day, bool) or not isinstance(day, int) or day < 1:
            raise ValueError("trip days must be positive integers")
    for earlier, later in zip(trip_days, trip_days[1:]):
        if later <= earlier:
            raise ValueError("trip days must be strictly increasing")
    if not passes:
        raise ValueError("at least one pass kind is required")
    for cover in passes:
        span = cover["span"]
        cost = cover["cost"]
        if isinstance(span, bool) or not isinstance(span, int) or span < 1:
            raise ValueError("pass span must be a positive integer")
        if isinstance(cost, bool) or not isinstance(cost, int) or cost < 0:
            raise ValueError("pass cost must be a non-negative integer")


def cheapest_pass_plan(trip_days: list, passes: list) -> dict:
    """One cheapest plan of passes covering every trip day."""
    _validate_plan(trip_days, passes)
    count = len(trip_days)
    best = [0] * (count + 1)
    choice = [0] * count
    for i in range(count - 1, -1, -1):
        best[i] = None
        for p, cover in enumerate(passes):
            expiry = trip_days[i] + cover["span"]
            nxt = i
            while nxt < count and trip_days[nxt] < expiry:
                nxt += 1
            candidate = cover["cost"] + best[nxt]
            if best[i] is None or candidate < best[i]:
                best[i] = candidate
                choice[i] = p
    purchases = []
    at = 0
    while at < count:
        bought = passes[choice[at]]
        purchases.append([trip_days[at], bought["span"]])
        expiry = trip_days[at] + bought["span"]
        while at < count and trip_days[at] < expiry:
            at += 1
    return {"total": best[0], "purchases": purchases}
