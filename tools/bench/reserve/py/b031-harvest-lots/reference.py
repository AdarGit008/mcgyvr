"""Fill a produce order from storage lots, freshest expiry first."""


def pick_harvest_lots(lots, needed, cap, today):
    def whole(value):
        return not isinstance(value, bool) and isinstance(value, int)

    if not whole(needed) or needed <= 0:
        raise ValueError("order quantity must be a positive integer")
    if not whole(cap) or cap <= 0:
        raise ValueError("per-lot cap must be a positive integer")
    if not whole(today):
        raise ValueError("current day must be an integer")
    seen = set()
    usable = []
    skipped = []
    for lot in lots:
        if not isinstance(lot, list) or len(lot) != 4:
            raise ValueError("a lot must be a [name, expiry, cost, quantity] quadruple")
        name, expiry, unit_cost, quantity = lot
        if not isinstance(name, str) or not name:
            raise ValueError("lot name must be a non-empty string")
        if name in seen:
            raise ValueError("repeated lot name: " + name)
        seen.add(name)
        if not whole(expiry):
            raise ValueError("expiry day must be an integer")
        if not whole(unit_cost) or unit_cost < 0:
            raise ValueError("unit cost must be a non-negative integer")
        if not whole(quantity) or quantity <= 0:
            raise ValueError("lot quantity must be a positive integer")
        if expiry > today:
            usable.append([name, expiry, unit_cost, quantity])
        else:
            skipped.append(name)
    def rank(entry):
        name, expiry, unit_cost, quantity = entry
        return (expiry, unit_cost, name)

    usable.sort(key=rank)
    picks = []
    leftovers = []
    cost = 0
    remaining = needed
    for name, expiry, unit_cost, quantity in usable:
        taken = quantity if quantity < cap else cap
        if taken > remaining:
            taken = remaining
        if taken > 0:
            picks.append([name, taken])
            cost += taken * unit_cost
            remaining -= taken
        if quantity - taken > 0:
            leftovers.append([name, quantity - taken])
    return {
        "picks": picks,
        "cost": cost,
        "shortfall": remaining,
        "skipped": skipped,
        "leftovers": leftovers,
    }
