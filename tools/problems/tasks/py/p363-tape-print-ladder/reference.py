"""The printed lots at each limit once the flow has worked the ladder."""


def _read_ticket(raw, at, refs):
    if not isinstance(raw, dict):
        raise ValueError("a ticket must be a mapping")
    ref = raw.get("ref")
    if not isinstance(ref, str) or ref == "":
        raise ValueError("a ticket needs a non-empty ref")
    if ref in refs:
        raise ValueError("two tickets carry the same ref")
    refs.add(ref)
    way = raw.get("way")
    if way not in ("buy", "sell"):
        raise ValueError("a way must be buy or sell")
    limit = raw.get("limit")
    lots = raw.get("lots")
    for value in (limit, lots):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("limit and lots must be positive whole numbers")
    return {"ref": ref, "way": way, "limit": limit, "lots": lots, "at": at}


def fold_tape_prints(opening: list, flow: list) -> dict:
    if not isinstance(opening, list) or not isinstance(flow, list):
        raise ValueError("both arguments must be lists")
    refs = set()
    ladder = [_read_ticket(raw, at, refs) for at, raw in enumerate(opening)]
    prints = {}
    at = len(ladder)

    for raw in flow:
        taker = _read_ticket(raw, at, refs)
        at += 1
        buying = taker["way"] == "buy"
        far = [
            ticket
            for ticket in ladder
            if ticket["way"] != taker["way"]
            and (
                ticket["limit"] <= taker["limit"]
                if buying
                else ticket["limit"] >= taker["limit"]
            )
        ]
        far.sort(key=lambda t: (t["limit"] if buying else -t["limit"], t["at"]))
        left = taker["lots"]
        for ticket in far:
            if left == 0:
                break
            lots = min(left, ticket["lots"])
            prints[ticket["limit"]] = prints.get(ticket["limit"], 0) + lots
            ticket["lots"] -= lots
            left -= lots
        ladder = [ticket for ticket in ladder if ticket["lots"] > 0]
        if left > 0:
            rested = dict(taker)
            rested["lots"] = left
            ladder.append(rested)

    rows = [{"limit": limit, "lots": prints[limit]} for limit in sorted(prints)]
    rest = 0
    for ticket in ladder:
        rest += ticket["lots"]
    return {"prints": rows, "left": rest}
