"""Where each ruled library should land."""

import re

_GROUP = re.compile(r"[0-9]+")


def _read_release(text: object) -> tuple:
    if not isinstance(text, str):
        raise ValueError("a release must be a string")
    parts = text.split(".")
    if len(parts) != 2:
        raise ValueError("a release must have two groups")
    pair = []
    for part in parts:
        if _GROUP.fullmatch(part) is None:
            raise ValueError("a release group must be digits")
        if len(part) > 1 and part.startswith("0"):
            raise ValueError("a release group must not carry a leading zero")
        pair.append(int(part))
    return tuple(pair)


def choose_upgrades(request: dict) -> dict:
    if not isinstance(request, dict):
        raise ValueError("the request must be a mapping")
    raw_installed = request.get("installed")
    raw_offers = request.get("offers")
    raw_rules = request.get("rules")
    if not isinstance(raw_installed, dict):
        raise ValueError("installed must be a mapping")
    if not isinstance(raw_offers, dict):
        raise ValueError("offers must be a mapping")
    if not isinstance(raw_rules, list):
        raise ValueError("rules must be a list")

    carried = {}
    for name, listed in raw_offers.items():
        if not isinstance(listed, list) or not listed:
            raise ValueError("an offers entry must be a non-empty list")
        texts = set()
        releases = []
        for text in listed:
            pair = _read_release(text)
            if text in texts:
                raise ValueError("an offers entry repeats a release")
            texts.add(text)
            releases.append((text, pair))
        carried[name] = releases

    running = {}
    for name, text in raw_installed.items():
        if name not in carried:
            raise ValueError("a library running today is not carried by the registry")
        running[name] = (text, _read_release(text))

    bounds = {}
    for raw in raw_rules:
        if not isinstance(raw, dict):
            raise ValueError("a rule must be a mapping")
        name = raw.get("package")
        if not isinstance(name, str) or name not in carried:
            raise ValueError("a rule bounds a library the registry does not carry")
        low = _read_release(raw.get("min"))
        high = _read_release(raw.get("max"))
        if low > high:
            raise ValueError("a rule's min is above its max")
        bounds.setdefault(name, []).append((low, high))

    moves = []
    snags = []
    for name in sorted(bounds):
        rules = bounds[name]
        allowed = [
            (text, pair)
            for text, pair in carried[name]
            if all(low <= pair <= high for low, high in rules)
        ]
        here = running.get(name)
        if here is None:
            if not allowed:
                snags.append({"package": name, "why": "none"})
            else:
                lowest = min(allowed, key=lambda entry: entry[1])
                moves.append({"package": name, "to": lowest[0], "action": "fetch"})
            continue
        if any(pair == here[1] for _, pair in allowed):
            moves.append({"package": name, "to": here[0], "action": "hold"})
            continue
        above = [entry for entry in allowed if entry[1] > here[1]]
        if above:
            lowest = min(above, key=lambda entry: entry[1])
            moves.append({"package": name, "to": lowest[0], "action": "lift"})
        elif allowed:
            snags.append({"package": name, "why": "drop"})
        else:
            snags.append({"package": name, "why": "none"})
    return {"moves": moves, "snags": snags}
