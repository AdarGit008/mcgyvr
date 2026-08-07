NAMES = ("code", "from", "to", "depart", "arrive")


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _label(value):
    return isinstance(value, str) and value != ""


def _preferred(candidate, held):
    if candidate[0] != held[0]:
        return candidate[0] < held[0]
    if len(candidate[1]) != len(held[1]):
        return len(candidate[1]) < len(held[1])
    return candidate[1] < held[1]


def connect_services(services, origin, destination, ready_at, min_transfer) -> dict:
    if not isinstance(services, list):
        raise ValueError("the timetable must be a list")
    if not _label(origin) or not _label(destination):
        raise ValueError("origin and destination must be non-empty strings")
    if origin == destination:
        raise ValueError("origin and destination must differ")
    if not _whole(ready_at) or ready_at < 0:
        raise ValueError("ready_at must be a whole number of zero or more")
    if not _whole(min_transfer) or min_transfer < 0:
        raise ValueError("min_transfer must be a whole number of zero or more")

    table = []
    codes = set()
    for raw in services:
        if not isinstance(raw, dict):
            raise ValueError("a service must be a record")
        for name in NAMES:
            if name not in raw:
                raise ValueError("a service is missing " + name)
        if not _label(raw["code"]):
            raise ValueError("a code must be a non-empty string")
        if not _label(raw["from"]) or not _label(raw["to"]):
            raise ValueError("a place must be a non-empty string")
        if raw["from"] == raw["to"]:
            raise ValueError("a service must not set down where it picked up")
        if not _whole(raw["depart"]) or not _whole(raw["arrive"]):
            raise ValueError("depart and arrive must be whole numbers")
        if raw["arrive"] <= raw["depart"]:
            raise ValueError("arrive must be later than depart")
        if raw["code"] in codes:
            raise ValueError("two services share the code " + raw["code"])
        codes.add(raw["code"])
        table.append(
            (raw["code"], raw["from"], raw["to"], raw["depart"], raw["arrive"])
        )

    best = None
    called = {origin}
    ridden = []

    def ride(here, arrived_at, earliest):
        nonlocal best
        if here == destination:
            found = (arrived_at, list(ridden))
            if best is None or _preferred(found, best):
                best = found
            return
        for code, start, finish, depart, arrive in table:
            if start != here:
                continue
            if depart < earliest:
                continue
            if finish in called:
                continue
            called.add(finish)
            ridden.append(code)
            ride(finish, arrive, arrive + min_transfer)
            ridden.pop()
            called.discard(finish)

    ride(origin, ready_at, ready_at)
    if best is None:
        return {"arrive": -1, "legs": []}
    return {"arrive": best[0], "legs": best[1]}
