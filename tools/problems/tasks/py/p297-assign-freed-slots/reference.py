TIERS = ("urgent", "soon", "routine")
WINDOWS = ("morning", "afternoon", "either")
PARTS = ("morning", "afternoon")


def assign_freed_slots(standby: list[dict], cancellations: list[dict]) -> list[dict]:
    if not isinstance(standby, list) or not isinstance(cancellations, list):
        raise ValueError("assign_freed_slots expects two lists")
    names: set[str] = set()
    for one in standby:
        if not isinstance(one, dict) or not isinstance(one.get("name"), str):
            raise ValueError("a patient needs a name")
        if one.get("tier") not in TIERS or one.get("window") not in WINDOWS:
            raise ValueError(f"a patient needs a known tier and window: {one}")
        waited = one.get("waited")
        if not isinstance(waited, int) or isinstance(waited, bool) or waited < 0:
            raise ValueError("waited is a whole number of zero or more")
        if one["name"] in names:
            raise ValueError(f"two patients share the name {one['name']}")
        names.add(one["name"])
    slots: set[str] = set()
    for call in cancellations:
        if not isinstance(call, dict) or not isinstance(call.get("slot"), str):
            raise ValueError("a cancellation needs a slot id")
        if call.get("part") not in PARTS:
            raise ValueError("a cancellation names morning or afternoon")
        if call["slot"] in slots:
            raise ValueError(f"two cancellations share the slot {call['slot']}")
        slots.add(call["slot"])
    placed: set[str] = set()
    placements: list[dict] = []
    for call in cancellations:
        winner = None
        for one in standby:
            if one["name"] in placed:
                continue
            if one["window"] != call["part"] and one["window"] != "either":
                continue
            if winner is None:
                winner = one
                continue
            here = TIERS.index(one["tier"])
            there = TIERS.index(winner["tier"])
            if here < there or (here == there and one["waited"] > winner["waited"]):
                winner = one
        if winner is None:
            continue
        placed.add(winner["name"])
        placements.append({"slot": call["slot"], "name": winner["name"]})
    return placements
