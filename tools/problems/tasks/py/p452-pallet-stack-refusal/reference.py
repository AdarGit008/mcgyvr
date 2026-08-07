def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def stack_pallet(items: list, limits: dict) -> dict:
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    if not isinstance(limits, dict):
        raise ValueError("limits must be a record")
    for key in ("deck", "roof"):
        if key not in limits or not _whole(limits[key]) or limits[key] < 1:
            raise ValueError(f"{key} must be a whole number above nought")

    named: set[str] = set()
    parcels: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("an item must be a record")
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("a name must be a non-empty string")
        if name in named:
            raise ValueError(f"two cartons answer to the name {name}")
        named.add(name)
        for key in ("mass", "high", "wide"):
            value = item.get(key)
            if not _whole(value) or value < 1:
                raise ValueError(f"{key} must be a whole number above nought")
        bears = item.get("bears")
        if not _whole(bears) or bears < 0:
            raise ValueError("bears must be a whole number of nought or more")
        if not isinstance(item.get("top"), bool):
            raise ValueError("top must be either true or false")
        parcels.append(
            {
                "name": name,
                "mass": item["mass"],
                "bears": bears,
                "high": item["high"],
                "wide": item["wide"],
                "top": item["top"],
            }
        )

    stacked: list[str] = []
    placed: list[dict] = []
    mass = 0
    high = 0
    for parcel in parcels:
        under = placed[-1] if placed else None
        reason = ""
        if under is not None and under["top"]:
            reason = "capped"
        elif under is not None and parcel["wide"] > under["wide"]:
            reason = "overhang"
        else:
            load = parcel["mass"]
            for below in reversed(placed):
                if load > below["bears"]:
                    reason = "crush"
                    break
                load += below["mass"]
        if not reason and mass + parcel["mass"] > limits["deck"]:
            reason = "deck"
        if not reason and high + parcel["high"] > limits["roof"]:
            reason = "roof"
        if reason:
            return {
                "stacked": stacked,
                "refused": parcel["name"],
                "reason": reason,
                "mass": mass,
                "high": high,
            }
        stacked.append(parcel["name"])
        placed.append(parcel)
        mass += parcel["mass"]
        high += parcel["high"]

    return {"stacked": stacked, "refused": "", "reason": "", "mass": mass, "high": high}
