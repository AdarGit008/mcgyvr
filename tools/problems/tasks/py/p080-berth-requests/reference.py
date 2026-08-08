def assign_berths(berths: list, quota: dict, requests: list) -> list:
    ids = set()
    for berth in berths:
        if berth["id"] in ids:
            raise ValueError("duplicate berth id: " + berth["id"])
        ids.add(berth["id"])
    occupant = [None] * len(berths)
    docked: dict = {}
    held: dict = {}
    results: list = []
    for request in requests:
        op = request["op"]
        if op == "dock":
            boat = request["boat"]
            owner = request["owner"]
            size = request["size"]
            if boat in docked:
                results.append("rejected:already_docked")
                continue
            if owner in quota and held.get(owner, 0) >= quota[owner]:
                results.append("rejected:over_quota")
                continue
            chosen = -1
            for i, berth in enumerate(berths):
                if occupant[i] is None and berth["size"] >= size:
                    chosen = i
                    break
            if chosen == -1:
                results.append("rejected:no_berth")
                continue
            occupant[chosen] = boat
            docked[boat] = (chosen, owner)
            held[owner] = held.get(owner, 0) + 1
            results.append(berths[chosen]["id"])
        elif op == "leave":
            boat = request["boat"]
            if boat not in docked:
                results.append("rejected:not_docked")
                continue
            index, owner = docked.pop(boat)
            occupant[index] = None
            held[owner] -= 1
            results.append("left")
        else:
            raise ValueError("unknown op: " + str(op))
    return results
