"""Which rule an already loaded deck breaks first."""


def _is_whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def audit_deck_load(rows: list, deck: dict) -> dict:
    if not isinstance(deck, dict):
        raise ValueError("deck must be a record")
    bays = deck.get("bays")
    if not isinstance(bays, list) or len(bays) == 0:
        raise ValueError("bays must be a list holding at least one bay")
    holds = {}
    levers = {}
    pulls = {}
    order = []
    for bay in bays:
        if not isinstance(bay, dict):
            raise ValueError("each bay must be a record")
        name = bay.get("bay")
        if not isinstance(name, str) or name == "":
            raise ValueError("a bay name must be a non-empty string")
        if name in holds:
            raise ValueError(f"two bays answer to the name {name}")
        hold = bay.get("hold")
        if not _is_whole(hold) or hold < 1:
            raise ValueError("hold must be a whole number above nought")
        pull = bay.get("pull")
        if not _is_whole(pull) or pull < 1:
            raise ValueError("pull must be a whole number above nought")
        lever = bay.get("lever")
        if not _is_whole(lever):
            raise ValueError("lever must be a whole number")
        holds[name] = hold
        levers[name] = lever
        pulls[name] = pull
        order.append(name)
    total = deck.get("total")
    if not _is_whole(total) or total < 1:
        raise ValueError("total must be a whole number above nought")

    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    seen = set()
    weights = {name: 0 for name in order}
    weight = 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each row must be a record")
        crate = row.get("crate")
        if not isinstance(crate, str) or crate == "":
            raise ValueError("crate must be a non-empty string")
        if crate in seen:
            raise ValueError(f"two rows answer to the crate {crate}")
        seen.add(crate)
        where = row.get("bay")
        if not isinstance(where, str) or where == "":
            raise ValueError("a row's bay must be a non-empty string")
        if where not in weights:
            raise ValueError(f"the deck lists no bay called {where}")
        load = row.get("weight")
        if not _is_whole(load) or load < 1:
            raise ValueError("weight must be a whole number above nought")
        weights[where] += load
        weight += load

    swing = sum(weights[name] * levers[name] for name in order)
    for name in order:
        if weights[name] > holds[name]:
            return {
                "verdict": "broken",
                "bay": name,
                "limit": "hold",
                "weight": weight,
                "swing": swing,
            }
        if abs(weights[name] * levers[name]) > pulls[name]:
            return {
                "verdict": "broken",
                "bay": name,
                "limit": "pull",
                "weight": weight,
                "swing": swing,
            }
    if weight > total:
        return {
            "verdict": "broken",
            "bay": "",
            "limit": "total",
            "weight": weight,
            "swing": swing,
        }
    return {
        "verdict": "clear",
        "bay": "",
        "limit": "",
        "weight": weight,
        "swing": swing,
    }
