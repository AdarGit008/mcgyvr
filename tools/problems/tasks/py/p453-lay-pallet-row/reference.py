def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def lay_pallet_row(boxes: list, deck: dict) -> dict:
    if not isinstance(boxes, list):
        raise ValueError("boxes must be a list")
    if not isinstance(deck, dict):
        raise ValueError("deck must be a record")
    for key in ("run", "span"):
        if key not in deck or not _whole(deck[key]) or deck[key] < 1:
            raise ValueError(f"{key} must be a whole number above nought")
    if "load" not in deck or not _whole(deck["load"]) or deck["load"] < 0:
        raise ValueError("load must be a whole number of nought or more")

    seen: set[str] = set()
    for box in boxes:
        if not isinstance(box, dict):
            raise ValueError("a box must be a record")
        name = box.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("a name must be a non-empty string")
        if name in seen:
            raise ValueError(f"two boxes answer to the name {name}")
        seen.add(name)
        for key in ("alen", "blen", "mass"):
            value = box.get(key)
            if not _whole(value) or value < 1:
                raise ValueError(f"{key} must be a whole number above nought")
        if not isinstance(box.get("tender"), bool):
            raise ValueError("tender must be either true or false")

    laid: list[str] = []
    skipped: list[str] = []
    run = deck["run"]
    mass = 0
    for box in boxes:
        if mass + box["mass"] > deck["load"]:
            skipped.append(box["name"])
            continue
        flat = box["alen"] <= run and box["blen"] <= deck["span"]
        turned = not box["tender"] and box["blen"] <= run and box["alen"] <= deck["span"]
        if flat:
            laid.append(f"{box['name']} flat")
            run -= box["alen"]
            mass += box["mass"]
        elif turned:
            laid.append(f"{box['name']} turned")
            run -= box["blen"]
            mass += box["mass"]
        else:
            skipped.append(box["name"])
    return {"laid": laid, "skipped": skipped, "run": run, "mass": mass}
