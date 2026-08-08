def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def plan_hoist_trips(hoists: list[dict], stops: list[int]) -> list[str]:
    if not isinstance(hoists, list) or not hoists:
        raise ValueError("hoists must be a non-empty list")
    if not isinstance(stops, list):
        raise ValueError("stops must be a list")

    order: list[str] = []
    rests: dict[str, int] = {}
    spent: dict[str, int] = {}
    for hoist in hoists:
        if not isinstance(hoist, dict):
            raise ValueError("a hoist must be a record")
        tag = hoist.get("tag")
        if not isinstance(tag, str) or not tag or tag == "idle":
            raise ValueError("a tag must be a non-empty string other than idle")
        if tag in rests:
            raise ValueError(f"tags repeat: {tag}")
        level = hoist.get("level")
        if not _whole(level) or level < 0:
            raise ValueError(f"resting level must be an integer of at least 0: {tag}")
        order.append(tag)
        rests[tag] = level
        spent[tag] = 0

    for stop in stops:
        if not _whole(stop) or stop < 0:
            raise ValueError("a stop must be an integer of at least 0")

    sheet: list[str] = []
    for stop in stops:
        chosen = ""
        least = 0
        for tag in order:
            if spent[tag] >= 12:
                continue
            at = rests[tag]
            cost = 2 * (stop - at) if stop > at else at - stop
            if chosen == "" or cost < least or (cost == least and tag < chosen):
                chosen = tag
                least = cost
        if chosen == "":
            sheet.append("idle")
            continue
        spent[chosen] += least
        rests[chosen] = stop
        sheet.append(chosen)
    return sheet
