def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def issue_cost_total(moves: list[dict]) -> int:
    if not isinstance(moves, list):
        raise ValueError("issue_cost_total expects a list of movements")
    bin_ = []
    on_hand = 0
    charged = 0
    for move in moves:
        if not isinstance(move, dict):
            raise ValueError("every movement is a record")
        kind = move.get("kind")
        if kind not in ("in", "out"):
            raise ValueError(f"unknown movement kind {kind!r}")
        units = move.get("units")
        if not _whole(units) or units <= 0:
            raise ValueError("units must be a whole number above zero")
        if kind == "in":
            cents = move.get("cents")
            if not _whole(cents) or cents < 0:
                raise ValueError("an arrival is priced in whole cents, not below zero")
            bin_.append([units, cents])
            on_hand += units
            continue
        if "cents" in move:
            raise ValueError("an issue carries no price of its own")
        if units > on_hand:
            raise ValueError("the bin does not hold that many parts")
        wanted = units
        while wanted > 0:
            consignment = bin_[0]
            taken = min(wanted, consignment[0])
            charged += taken * consignment[1]
            consignment[0] -= taken
            wanted -= taken
            on_hand -= taken
            if consignment[0] == 0:
                bin_.pop(0)
    return charged
