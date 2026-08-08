"""One line per row of a zoned pick walk."""


def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def zone_pick_walk(plan: dict) -> list:
    if not isinstance(plan, dict):
        raise ValueError("the plan must be a mapping")
    zone_order = plan.get("zoneOrder")
    if not isinstance(zone_order, list) or not zone_order:
        raise ValueError("zoneOrder must be a non-empty list")
    known = set()
    for zone in zone_order:
        if not isinstance(zone, str) or not zone:
            raise ValueError("a zone must be a non-empty string")
        if zone in known:
            raise ValueError("zoneOrder repeats a zone")
        known.add(zone)
    picks = plan.get("picks")
    if not isinstance(picks, list):
        raise ValueError("picks must be a list")
    codes = set()
    grabs = []
    for order, pick in enumerate(picks):
        if not isinstance(pick, dict):
            raise ValueError("a pick must be a mapping")
        code = pick.get("code")
        if not isinstance(code, str) or not code:
            raise ValueError("a code must be a non-empty string")
        if code in codes:
            raise ValueError("two picks share a code")
        codes.add(code)
        zone = pick.get("zone")
        if not isinstance(zone, str) or zone not in known:
            raise ValueError("a pick names a zone zoneOrder does not list")
        row = pick.get("row")
        slot = pick.get("slot")
        if not _whole(row) or row < 1:
            raise ValueError("a row must be a positive whole number")
        if not _whole(slot) or slot < 1:
            raise ValueError("a slot must be a positive whole number")
        grabs.append({"code": code, "zone": zone, "row": row, "slot": slot, "at": order})

    lines = []
    for zone in zone_order:
        group = [grab for grab in grabs if grab["zone"] == zone]
        if not group:
            continue
        rows = sorted({grab["row"] for grab in group})
        for entered, row in enumerate(rows):
            here = [grab for grab in group if grab["row"] == row]
            if entered % 2 == 0:
                here.sort(key=lambda grab: (grab["slot"], grab["at"]))
            else:
                here.sort(key=lambda grab: (-grab["slot"], grab["at"]))
            joined = "|".join(grab["code"] for grab in here)
            lines.append(zone + "/" + str(row) + ":" + joined)
    return lines
