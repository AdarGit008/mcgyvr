def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def prorate_plan_switch(
    cycle_days: int, move_day: int, paid_cents: int, plan_cents: int
) -> dict:
    if not _whole(cycle_days) or cycle_days < 1:
        raise ValueError("the cycle must be a whole number of one day or more")
    if not _whole(move_day) or move_day < 1 or move_day > cycle_days:
        raise ValueError("the day of the move must lie inside the cycle")
    for cents in (paid_cents, plan_cents):
        if not _whole(cents) or cents < 0:
            raise ValueError("a price must be a whole number of cents, nothing or more")
    unused = cycle_days - move_day + 1
    credit = (paid_cents * unused) // cycle_days
    charge = -((-plan_cents * unused) // cycle_days)
    due = charge - credit if charge > credit else 0
    carried = credit - charge if credit > charge else 0
    return {"credit": credit, "charge": charge, "due": due, "carried": carried}
