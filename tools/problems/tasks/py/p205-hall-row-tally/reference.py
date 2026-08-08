def tally_hall_rows(hall: list) -> list:
    if not isinstance(hall, list) or len(hall) == 0:
        raise ValueError("the hall must be a non-empty list of tiers")
    width = -1
    for tier in hall:
        if not isinstance(tier, str) or tier == "":
            raise ValueError("every tier must be a non-empty string")
        if width == -1:
            width = len(tier)
        elif len(tier) != width:
            raise ValueError("the tiers differ in width")
        for ch in tier:
            if ch not in ("x", "o", "="):
                raise ValueError("stray character in the hall: " + ch)

    lines = []
    held_all = 0
    open_all = 0
    widest = 0
    widest_open = -1
    for at, tier in enumerate(hall):
        held = tier.count("x")
        spare = tier.count("o")
        if held + spare == 0:
            raise ValueError("tier " + str(at) + " offers no chair whatsoever")
        lines.append("tier" + str(at) + " held=" + str(held) + " open=" + str(spare))
        held_all += held
        open_all += spare
        if spare > widest_open:
            widest_open = spare
            widest = at
    lines.append(
        "hall held="
        + str(held_all)
        + " open="
        + str(open_all)
        + " widest=tier"
        + str(widest)
    )
    return lines
