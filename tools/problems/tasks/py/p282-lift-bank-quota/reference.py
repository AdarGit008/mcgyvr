def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def assign_lift_calls(cars: list[dict], calls: list[int], top: int) -> list[str]:
    if not _whole(top) or top < 1:
        raise ValueError("top must be an integer of at least 1")
    if not isinstance(cars, list) or not cars:
        raise ValueError("cars must be a non-empty list")
    if not isinstance(calls, list):
        raise ValueError("calls must be a list")

    order: list[str] = []
    floors: dict[str, int] = {}
    quotas: dict[str, int] = {}
    for cage in cars:
        if not isinstance(cage, dict):
            raise ValueError("a cage must be a record")
        name = cage.get("name")
        if not isinstance(name, str) or not name or name == "-":
            raise ValueError("a cage name must be a non-empty string other than -")
        if name in floors:
            raise ValueError(f"cage names repeat: {name}")
        floor = cage.get("floor")
        if not _whole(floor) or floor < 0 or floor > top:
            raise ValueError(f"standing floor out of the building: {name}")
        quota = cage.get("quota")
        if not _whole(quota) or quota < 1:
            raise ValueError(f"quota must be an integer of at least 1: {name}")
        order.append(name)
        floors[name] = floor
        quotas[name] = quota

    for call in calls:
        if not _whole(call) or call < 0 or call > top:
            raise ValueError(f"call out of the building: {call}")

    answered = {name: 0 for name in order}
    sheet: list[str] = []
    for call in calls:
        best = ""
        for name in order:
            if answered[name] >= quotas[name]:
                continue
            if best == "":
                best = name
                continue
            here = abs(floors[name] - call)
            there = abs(floors[best] - call)
            if here != there:
                if here < there:
                    best = name
                continue
            if answered[name] != answered[best]:
                if answered[name] < answered[best]:
                    best = name
                continue
            if name < best:
                best = name
        if best == "":
            sheet.append("-")
            continue
        floors[best] = call
        answered[best] += 1
        sheet.append(best)
    return sheet
