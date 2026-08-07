MODES = ("dark", "live", "ramp")


def _text(value):
    return isinstance(value, str) and value != ""


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _roster(value, label):
    if not isinstance(value, list):
        raise ValueError(label + " must be a list")
    held = set()
    for one in value:
        if not _text(one):
            raise ValueError(label + " must hold non-empty strings")
        if one in held:
            raise ValueError(label + " names " + one + " twice")
        held.add(one)
    return held


def decide_switch(setting, caller) -> dict:
    if not isinstance(setting, dict) or not all(
        name in setting for name in ("mode", "barred", "waved", "cutoff")
    ):
        raise ValueError("a setting must carry mode, barred, waved and cutoff")
    if setting["mode"] not in MODES:
        raise ValueError("mode must be dark, live or ramp")
    barred = _roster(setting["barred"], "barred")
    waved = _roster(setting["waved"], "waved")
    both = barred & waved
    if both:
        raise ValueError(sorted(both)[0] + " is both barred and waved")
    cutoff = setting["cutoff"]
    if not _whole(cutoff) or cutoff < 0 or cutoff > 100:
        raise ValueError("cutoff must be a whole number from 0 to 100")
    if not isinstance(caller, dict) or "id" not in caller or "slot" not in caller:
        raise ValueError("a caller must be a record carrying id and slot")
    if not _text(caller["id"]):
        raise ValueError("id must be a non-empty string")
    slot = caller["slot"]
    if not _whole(slot) or slot < 0 or slot > 99:
        raise ValueError("slot must be a whole number from 0 to 99")

    if caller["id"] in barred:
        return {"open": "no", "why": "barred"}
    if setting["mode"] == "dark":
        return {"open": "no", "why": "dark"}
    if caller["id"] in waved:
        return {"open": "yes", "why": "waved"}
    if setting["mode"] == "live":
        return {"open": "yes", "why": "live"}
    if slot < cutoff:
        return {"open": "yes", "why": "ramp"}
    return {"open": "no", "why": "held"}
