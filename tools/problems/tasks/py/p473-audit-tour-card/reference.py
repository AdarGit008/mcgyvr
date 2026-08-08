def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def audit_tour_card(rooms: list, card: list, allowance: int) -> dict:
    if not isinstance(rooms, list):
        raise ValueError("audit_tour_card expects a list of rooms")
    if not isinstance(card, list):
        raise ValueError("the card is not a list")
    if not _whole(allowance) or allowance < 0:
        raise ValueError("the allowance is not whole or falls below nought")

    floor = []
    where = {}
    for entry in rooms:
        if not isinstance(entry, dict):
            raise ValueError("a room is not a mapping")
        if sorted(entry) != ["dwell", "hop", "merit", "room"]:
            raise ValueError("a room's keys are not exactly the four named")
        name = entry["room"]
        if not isinstance(name, str) or name == "":
            raise ValueError("a room name is not a non-empty string")
        if name in where:
            raise ValueError("a room name is repeated on the floor")
        hop = entry["hop"]
        if not _whole(hop) or hop < 0:
            raise ValueError("a hop is not whole or falls below nought")
        dwell = entry["dwell"]
        if not _whole(dwell) or dwell < 1:
            raise ValueError("a dwell is not whole or falls below one")
        merit = entry["merit"]
        if not _whole(merit) or merit < 0:
            raise ValueError("a merit is not whole or falls below nought")
        where[name] = len(floor)
        floor.append({"room": name, "hop": hop, "dwell": dwell, "merit": merit})

    last = -1
    dwelt = 0
    merit = 0
    for name in card:
        if not isinstance(name, str):
            raise ValueError("a card entry is not a string")
        if name not in where:
            raise ValueError("a card entry names no room on the floor")
        seat = where[name]
        if seat <= last:
            raise ValueError("a card repeats a name or falls out of floor-plan order")
        last = seat
        dwelt += floor[seat]["dwell"]
        merit += floor[seat]["merit"]

    walked = sum(room["hop"] for room in floor[: last + 1])

    minutes = walked + dwelt
    return {
        "minutes": minutes,
        "merit": merit,
        "spare": allowance - minutes,
        "ok": minutes <= allowance,
    }
