import re

PLANS = {
    "vela": (("who",), ("house", "street"), ("code", "town")),
    "korrin": (("who",), ("street", "house"), ("town",), ("code",)),
    "mebis": (("who",), ("ward",), ("street", "house"), ("town", "code")),
}

SHOUTED = {
    "vela": frozenset({"town"}),
    "korrin": frozenset({"who", "code"}),
    "mebis": frozenset({"who", "ward", "street", "house", "town", "code"}),
}


def _tidy(value):
    if not isinstance(value, str):
        return ""
    return re.sub(r" +", " ", value.strip())


def render_postal_lines(entry: dict, region: str) -> list:
    if not isinstance(entry, dict):
        raise ValueError("entry must be a record")
    if not isinstance(region, str) or region not in PLANS:
        raise ValueError(f"{region!r} is not one of vela, korrin, mebis")
    shouted = SHOUTED[region]
    lines = []
    for slots in PLANS[region]:
        pieces = []
        for slot in slots:
            value = _tidy(entry.get(slot))
            if value == "":
                raise ValueError(f"{region} needs {slot} and it is missing")
            pieces.append(value.upper() if slot in shouted else value)
        lines.append(" ".join(pieces))
    return lines
