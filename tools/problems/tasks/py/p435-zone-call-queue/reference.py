def build_zone_queue(zones: list, travellers: list) -> dict:
    if not isinstance(zones, list) or not isinstance(travellers, list):
        raise ValueError("build_zone_queue expects two lists")
    if not zones:
        raise ValueError("the gate calls at least one zone")
    rank: dict = {}
    for label in zones:
        if not isinstance(label, str) or label == "":
            raise ValueError("a zone label is a non-empty string")
        if label in rank:
            raise ValueError(f"the calling order writes {label} twice")
        rank[label] = len(rank)

    units: list = []
    by_party: dict = {}
    names: set = set()
    for row in travellers:
        if not isinstance(row, dict):
            raise ValueError("a traveller is a mapping")
        name = row.get("name")
        zone = row.get("zone")
        party = row.get("party")
        early = row.get("early")
        if not isinstance(name, str) or name == "":
            raise ValueError("a name is a non-empty string")
        if name in names:
            raise ValueError(f"two travellers answer to {name}")
        names.add(name)
        if not isinstance(party, str):
            raise ValueError("a party is a string")
        if not isinstance(early, bool):
            raise ValueError("early is a boolean")
        if not isinstance(zone, str) or zone not in rank:
            raise ValueError("no call is made for that zone")
        seat = rank[zone]
        if party == "":
            units.append({"members": [], "earliest": seat, "early": False})
            unit = units[-1]
        else:
            found = by_party.get(party)
            if found is None:
                units.append({"members": [], "earliest": seat, "early": False})
                by_party[party] = len(units) - 1
                unit = units[-1]
            else:
                unit = units[found]
        unit["members"].append(name)
        unit["earliest"] = min(unit["earliest"], seat)
        unit["early"] = unit["early"] or early

    queue: list = []
    calls: list = [0] * len(zones)
    preboard: list = []
    for unit in units:
        if unit["early"]:
            preboard.extend(unit["members"])
    queue.extend(sorted(preboard))
    for step in range(len(zones)):
        for unit in units:
            if unit["early"] or unit["earliest"] != step:
                continue
            walking = sorted(unit["members"])
            queue.extend(walking)
            calls[step] += len(walking)
    return {"queue": queue, "calls": calls}
