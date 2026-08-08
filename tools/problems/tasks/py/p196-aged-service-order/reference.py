def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def aged_service_order(events: list, step: int) -> list:
    if not _whole(step) or step <= 0:
        raise ValueError("the aging step must be a positive whole number")
    if not isinstance(events, list) or not events:
        raise ValueError("the log is empty")
    room = []
    taken = []
    previous = -1
    for moment in events:
        if not isinstance(moment, dict):
            raise ValueError("a moment must be a mapping")
        tick = moment.get("tick")
        if not _whole(tick) or tick < 0:
            raise ValueError("a tick is a non-negative whole number")
        if tick < previous:
            raise ValueError("tick " + str(tick) + " runs backwards")
        previous = tick
        kind = moment.get("kind")
        if kind == "join":
            who = moment.get("who")
            if not isinstance(who, str) or not who:
                raise ValueError("a joining caller needs a name")
            rank = moment.get("rank")
            if not _whole(rank) or rank < 0:
                raise ValueError("a rank is a non-negative whole number")
            if any(entry["who"] == who for entry in room):
                raise ValueError(who + " is already in the waiting room")
            room.append({"who": who, "rank": rank, "since": tick})
        elif kind == "call":
            if not room:
                raise ValueError("a call found the waiting room empty")
            chosen = 0
            best = room[0]["rank"] + (tick - room[0]["since"]) // step
            for index in range(1, len(room)):
                entry = room[index]
                standing = entry["rank"] + (tick - entry["since"]) // step
                held = room[chosen]
                if standing > best:
                    best = standing
                    chosen = index
                elif standing == best and (
                    entry["since"] < held["since"]
                    or (entry["since"] == held["since"] and entry["who"] < held["who"])
                ):
                    chosen = index
            taken.append(room[chosen]["who"])
            room.pop(chosen)
        else:
            raise ValueError("unknown moment kind: " + str(kind))
    return taken
