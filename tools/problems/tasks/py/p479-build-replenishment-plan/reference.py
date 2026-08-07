def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def build_replenishment_plan(item: dict, draws: list) -> dict:
    if not isinstance(item, dict):
        raise ValueError("build_replenishment_plan expects an item mapping")
    if sorted(item) != ["ceiling", "floor", "held", "inbound", "lead", "pack"]:
        raise ValueError("the item's keys are not exactly the six named")
    levels = {}
    for field in ("held", "floor", "ceiling"):
        value = item[field]
        if not _whole(value) or value < 0:
            raise ValueError("a held, floor or ceiling is not whole or falls below nought")
        levels[field] = value
    if levels["ceiling"] < levels["floor"]:
        raise ValueError("the ceiling falls below the floor")
    pack = item["pack"]
    if not _whole(pack) or pack < 1:
        raise ValueError("the pack is not whole or falls below one")
    lead = item["lead"]
    if not _whole(lead) or lead < 1:
        raise ValueError("the lead is not whole or falls below one")
    inbound = item["inbound"]
    if not isinstance(inbound, list):
        raise ValueError("the inbound is not a list")
    if not isinstance(draws, list):
        raise ValueError("the draws are not a list")

    landings = {}
    pending = 0
    latest = 0
    for entry in inbound:
        if not isinstance(entry, dict):
            raise ValueError("an inbound entry is not a mapping")
        if sorted(entry) != ["units", "week"]:
            raise ValueError("an inbound entry's keys are not exactly week and units")
        week = entry["week"]
        if not _whole(week) or week < 1:
            raise ValueError("an inbound week is not whole or falls below one")
        if week <= latest:
            raise ValueError("the inbound weeks do not climb strictly")
        latest = week
        units = entry["units"]
        if not _whole(units) or units < 1:
            raise ValueError("an inbound units is not whole or falls below one")
        landings[week] = landings.get(week, 0) + units
        pending += units

    depot = levels["held"]
    missed = 0
    orders = []
    for week in range(1, len(draws) + 1):
        draw = draws[week - 1]
        if not _whole(draw) or draw < 0:
            raise ValueError("a draw is not whole or falls below nought")
        landed = landings.get(week, 0)
        depot += landed
        pending -= landed
        if draw > depot:
            missed += draw - depot
            depot = 0
        else:
            depot -= draw
        cover = depot + pending
        if cover > levels["floor"]:
            continue
        want = levels["ceiling"] - cover
        if want <= 0:
            continue
        units = -(-want // pack) * pack
        orders.append({"week": week, "units": units})
        pending += units
        lands = week + lead
        landings[lands] = landings.get(lands, 0) + units

    return {"orders": orders, "missed": missed, "closing": depot}
