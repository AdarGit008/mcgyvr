import re

_GROUP = re.compile(r"[0-9]+")


def _read_version(text: object) -> tuple:
    if not isinstance(text, str):
        raise ValueError("a version must be a string")
    parts = text.split(".")
    if len(parts) != 3:
        raise ValueError("a version must have three groups")
    trip = []
    for part in parts:
        if _GROUP.fullmatch(part) is None:
            raise ValueError("a version group must be digits")
        if len(part) > 1 and part.startswith("0"):
            raise ValueError("a version group must not carry a leading zero")
        trip.append(int(part))
    return tuple(trip)


def _read_want(raw: object, stock: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("a want must be a mapping")
    name = raw.get("name")
    if not isinstance(name, str) or name not in stock:
        raise ValueError("a want names a package the shelf does not stock")
    low = _read_version(raw.get("from"))
    high = _read_version(raw.get("under"))
    if not low < high:
        raise ValueError("a want's from must be strictly below its under")
    return {"name": name, "from": low, "under": high}


def pin_package_set(plan: dict) -> dict:
    if not isinstance(plan, dict):
        raise ValueError("the plan must be a mapping")
    shelf = plan.get("shelf")
    needs = plan.get("needs")
    root = plan.get("root")
    if not isinstance(shelf, dict):
        raise ValueError("shelf must be a mapping")
    if not isinstance(needs, dict):
        raise ValueError("needs must be a mapping")
    if not isinstance(root, list):
        raise ValueError("root must be a list")

    stock = {}
    for name, listed in shelf.items():
        if not isinstance(listed, list) or not listed:
            raise ValueError("a shelf entry must be a non-empty list")
        texts = set()
        versions = []
        for text in listed:
            trip = _read_version(text)
            if text in texts:
                raise ValueError("a shelf entry repeats a version")
            texts.add(text)
            versions.append((text, trip))
        stock[name] = versions

    declared = {}
    for name, listed in needs.items():
        if name not in stock:
            raise ValueError("needs is keyed by a package the shelf does not stock")
        if not isinstance(listed, list):
            raise ValueError("a declared want list must be a list")
        declared[name] = [_read_want(raw, stock) for raw in listed]
    queue = [_read_want(raw, stock) for raw in root]

    filed = {}
    reached = set()
    head = 0
    while head < len(queue):
        want = queue[head]
        head += 1
        filed.setdefault(want["name"], []).append(want)
        if want["name"] not in reached:
            reached.add(want["name"])
            queue.extend(declared.get(want["name"], []))

    picked = []
    stuck = []
    for name in sorted(reached):
        windows = filed[name]
        allowed = [
            (text, trip)
            for text, trip in stock[name]
            if all(want["from"] <= trip < want["under"] for want in windows)
        ]
        if not allowed:
            stuck.append(name)
            continue
        best = min(allowed, key=lambda pair: (pair[1][0], -pair[1][1], -pair[1][2]))
        picked.append({"name": name, "version": best[0]})
    return {"picked": picked, "stuck": stuck}
