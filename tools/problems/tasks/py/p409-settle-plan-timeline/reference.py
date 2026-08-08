def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def settle_plan_timeline(period_days: int, opening_cents: int, changes: list) -> dict:
    if not _whole(period_days) or period_days < 1:
        raise ValueError("the period must be a whole number of one day or more")
    if not _whole(opening_cents) or opening_cents < 0:
        raise ValueError("the opening price must be a whole number of cents")
    if not isinstance(changes, list):
        raise ValueError("the changes must be a list")
    previous_day = 1
    taken = []
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError("a change must be a record")
        day = change.get("day")
        if not _whole(day) or day < 2 or day > period_days:
            raise ValueError("a change day must lie from two to the period's last day")
        if day <= previous_day:
            raise ValueError("the change days must climb strictly")
        previous_day = day
        cents = change.get("cents")
        if not _whole(cents) or cents < 0:
            raise ValueError("a change price must be a whole number of cents")
        taken.append((day, cents))
    legs = []
    total = 0
    pot = 0
    start = 1
    rate = opening_cents
    for index in range(len(taken) + 1):
        end = period_days if index == len(taken) else taken[index][0] - 1
        days = end - start + 1
        product = rate * days
        cents = product // period_days
        pot += product % period_days
        if pot >= period_days:
            cents += 1
            pot -= period_days
        legs.append({"from": start, "to": end, "days": days, "cents": cents})
        total += cents
        if index < len(taken):
            start, rate = taken[index]
    return {"legs": legs, "total": total}
