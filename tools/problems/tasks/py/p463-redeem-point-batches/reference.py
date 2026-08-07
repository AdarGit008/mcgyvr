def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def redeem_point_batches(events: list) -> dict:
    if not isinstance(events, list):
        raise ValueError("redeem_point_batches expects a list of events")

    batches = []
    taken = []
    lapsed = 0
    seq = 0
    clock = 0
    started = False

    for event in events:
        if not isinstance(event, dict):
            raise ValueError("an event is not a mapping")
        kind = event.get("kind")
        if kind not in ("earn", "burn"):
            raise ValueError("an event's kind is outside earn and burn")
        wanted = (
            ["day", "kind", "life", "points"]
            if kind == "earn"
            else ["day", "kind", "points"]
        )
        if sorted(event) != wanted:
            raise ValueError("an event's keys are not the ones its kind calls for")
        day = event["day"]
        if not _whole(day) or day < 0:
            raise ValueError("a day is not whole or falls below nought")
        if started and day < clock:
            raise ValueError("a day steps backwards")
        clock = day
        started = True
        points = event["points"]
        if not _whole(points) or points < 1:
            raise ValueError("points are not whole or fall below one")

        alive = []
        for batch in batches:
            if batch["last"] < clock:
                lapsed += batch["left"]
            else:
                alive.append(batch)
        batches = alive

        if kind == "earn":
            life = event["life"]
            if not _whole(life) or life < 0:
                raise ValueError("a life is not whole or falls below nought")
            batches.append({"last": clock + life, "seq": seq, "left": points})
            seq += 1
            continue

        held = sum(batch["left"] for batch in batches)
        if held < points:
            taken.append(0)
            continue
        need = points
        for batch in sorted(batches, key=lambda b: (b["last"], b["seq"])):
            if need == 0:
                break
            drawn = min(batch["left"], need)
            batch["left"] -= drawn
            need -= drawn
        batches = [batch for batch in batches if batch["left"] > 0]
        taken.append(points)

    return {
        "taken": taken,
        "lapsed": lapsed,
        "balance": sum(batch["left"] for batch in batches),
    }
