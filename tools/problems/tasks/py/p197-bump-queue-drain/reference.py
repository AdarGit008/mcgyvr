"""The order a crew works through a batch of graded tickets."""

CEILING = 9


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _urgency(ticket: dict, minute: int, bump_every: int) -> int:
    raw = ticket["grade"] + (minute - ticket["filed"]) // bump_every
    return CEILING if raw > CEILING else raw


def bump_queue_drain(tickets: list, start: int, bump_every: int) -> list:
    if not _whole(start) or start < 0:
        raise ValueError("the start minute is a non-negative whole number")
    if not _whole(bump_every) or bump_every <= 0:
        raise ValueError("the bump interval is a positive whole number")
    if not isinstance(tickets, list) or not tickets:
        raise ValueError("the batch is empty")
    pending = []
    ids = set()
    for raw in tickets:
        if not isinstance(raw, dict):
            raise ValueError("a ticket must be a mapping")
        identifier = raw.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("a ticket needs an id")
        if identifier in ids:
            raise ValueError("repeated ticket id: " + identifier)
        ids.add(identifier)
        filed = raw.get("filed")
        if not _whole(filed) or filed < 0:
            raise ValueError("a filed minute is a non-negative whole number")
        grade = raw.get("grade")
        if not _whole(grade) or grade < 0 or grade > CEILING:
            raise ValueError("a grade runs from 0 to " + str(CEILING))
        pending.append({"id": identifier, "filed": filed, "grade": grade})

    handled = []
    minute = start
    while pending:
        pick = -1
        for i, ticket in enumerate(pending):
            if ticket["filed"] > minute:
                continue
            if pick == -1:
                pick = i
                continue
            here = _urgency(ticket, minute, bump_every)
            held = _urgency(pending[pick], minute, bump_every)
            if here > held:
                pick = i
            elif here == held and (
                ticket["filed"] < pending[pick]["filed"]
                or (
                    ticket["filed"] == pending[pick]["filed"]
                    and ticket["id"] < pending[pick]["id"]
                )
            ):
                pick = i
        if pick != -1:
            handled.append(pending[pick]["id"])
            pending.pop(pick)
        minute += 1
    return handled
