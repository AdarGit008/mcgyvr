def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def place_donations(requests, lots):
    request_ids = set()
    for request in requests:
        if request["id"] in request_ids:
            raise ValueError("repeated request id")
        request_ids.add(request["id"])
        if not _integer(request["from"]) or not _integer(request["to"]):
            raise ValueError("from and to must be integers")
        if request["from"] > request["to"]:
            raise ValueError("a span with from greater than to is malformed")
    lot_ids = set()
    open_flags = [True] * len(requests)
    placed = []
    for entry in lots:
        if entry["id"] in lot_ids:
            raise ValueError("repeated lot id")
        lot_ids.add(entry["id"])
        if not _integer(entry["day"]):
            raise ValueError("day must be an integer")
        best = -1
        for index, request in enumerate(requests):
            if not open_flags[index]:
                continue
            fits = (
                request["from"] <= entry["day"] <= request["to"]
                and (entry["kind"] == "ANY" or entry["kind"] == request["kind"])
            )
            if not fits:
                continue
            if best == -1:
                best = index
                continue
            leader = requests[best]
            wins = (request["urgent"] and not leader["urgent"]) or (
                request["urgent"] == leader["urgent"]
                and request["to"] < leader["to"]
            )
            if wins:
                best = index
        if best != -1:
            open_flags[best] = False
            placed.append([entry["id"], requests[best]["id"]])
    return placed
