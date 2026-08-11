def kind_weight(kind: str) -> int:
    if kind == "steel":
        return 10
    if kind == "wood":
        return 4
    return 1


def top_load(kinds: list[str]) -> str:
    """The kind carrying the greatest weight once counted together."""
    totals = {}
    arrived = []
    for kind in kinds:
        if kind not in totals:
            totals[kind] = 0
            arrived.append(kind)
        totals[kind] += kind_weight(kind)
    named = ""
    greatest = 0
    for kind in arrived:
        if totals[kind] > greatest:
            named = kind
            greatest = totals[kind]
    return named
