def meter_charge(units: int, tiers: list) -> int:
    if isinstance(units, bool) or not isinstance(units, int):
        raise ValueError("units must be an integer")
    if units < 0:
        raise ValueError("units must not be negative")
    if not isinstance(tiers, list) or not tiers:
        raise ValueError("the ladder needs at least one tier")
    capacity = 0
    for span, rate in tiers:
        if isinstance(span, bool) or not isinstance(span, int) or span <= 0:
            raise ValueError("a tier span must be a positive integer")
        if isinstance(rate, bool) or not isinstance(rate, int) or rate < 0:
            raise ValueError("a tier rate must be a non-negative integer")
        capacity += span
    if units > capacity:
        raise ValueError("consumption exceeds the ladder")
    remaining = units
    cents = 0
    for span, rate in tiers:
        used = min(remaining, span)
        remaining -= used
        cents += (used * rate + 500) // 1000
    return cents
