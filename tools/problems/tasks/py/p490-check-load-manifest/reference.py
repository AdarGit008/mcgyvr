def _is_whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def check_load_manifest(items: list, plan: dict) -> dict:
    if not isinstance(plan, dict):
        raise ValueError("plan must be a record")
    zones = plan.get("zones")
    if not isinstance(zones, list) or len(zones) == 0:
        raise ValueError("zones must be a list holding at least one zone")
    caps = {}
    arms = {}
    order = []
    for zone in zones:
        if not isinstance(zone, dict):
            raise ValueError("each zone must be a record")
        name = zone.get("zone")
        if not isinstance(name, str) or name == "":
            raise ValueError("a zone name must be a non-empty string")
        if name in caps:
            raise ValueError(f"two zones answer to the name {name}")
        cap = zone.get("cap")
        if not _is_whole(cap) or cap < 1:
            raise ValueError("a cap must be a whole number above nought")
        arm = zone.get("arm")
        if not _is_whole(arm):
            raise ValueError("an arm must be a whole number")
        caps[name] = cap
        arms[name] = arm
        order.append(name)
    gross = plan.get("gross")
    if not _is_whole(gross) or gross < 1:
        raise ValueError("gross must be a whole number above nought")
    low = plan.get("low")
    high = plan.get("high")
    if not _is_whole(low) or not _is_whole(high):
        raise ValueError("low and high must be whole numbers")
    if low > high:
        raise ValueError("low must be no greater than high")

    if not isinstance(items, list):
        raise ValueError("items must be a list")
    seen = set()
    manifest = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each item must be a record")
        tag = item.get("tag")
        if not isinstance(tag, str) or tag == "":
            raise ValueError("tag must be a non-empty string")
        if tag in seen:
            raise ValueError(f"two items answer to the tag {tag}")
        seen.add(tag)
        where = item.get("zone")
        if not isinstance(where, str) or where == "":
            raise ValueError("an item's zone must be a non-empty string")
        if where not in caps:
            raise ValueError(f"the plan names no zone called {where}")
        mass = item.get("mass")
        if not _is_whole(mass) or mass < 1:
            raise ValueError("mass must be a whole number above nought")
        manifest.append((tag, where, mass))

    per_zone = {name: 0 for name in order}
    loaded = []
    total = 0
    moment = 0
    stopped = ""
    limit = ""
    for tag, where, mass in manifest:
        zone_mass = per_zone[where] + mass
        hold_mass = total + mass
        swing = moment + mass * arms[where]
        if zone_mass > caps[where]:
            limit = "cap"
        elif hold_mass > gross:
            limit = "gross"
        elif swing < low or swing > high:
            limit = "moment"
        if limit != "":
            stopped = tag
            break
        per_zone[where] = zone_mass
        total = hold_mass
        moment = swing
        loaded.append(tag)

    return {
        "loaded": loaded,
        "stopped": stopped,
        "limit": limit,
        "mass": total,
        "moment": moment,
        "zones": [{"zone": name, "mass": per_zone[name]} for name in order],
    }
