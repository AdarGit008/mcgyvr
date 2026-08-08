def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def band_parcel_charge(book: dict, parcel: dict) -> dict:
    if not isinstance(book, dict):
        raise ValueError("the book must be a mapping")
    if not isinstance(parcel, dict):
        raise ValueError("the parcel must be a mapping")

    zones = book.get("zones")
    if not isinstance(zones, list) or not zones:
        raise ValueError("the zones must be a non-empty list")
    zone_at = {}
    for zone in zones:
        if not isinstance(zone, str) or not zone:
            raise ValueError("a zone must be a non-empty name")
        if zone in zone_at:
            raise ValueError("a zone is listed twice")
        zone_at[zone] = len(zone_at)

    steps = book.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("the bands must be a non-empty list")
    up_to = []
    prices = []
    previous = 0
    for at, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError("a band must be a mapping")
        edge = step.get("upTo")
        if edge is None:
            if at != len(steps) - 1:
                raise ValueError("the open band must be the last band")
        else:
            if not _whole(edge) or edge <= 0:
                raise ValueError("a stated weight must be a positive whole number")
            if edge <= previous:
                raise ValueError("the stated weights must climb strictly")
            previous = edge
        cents = step.get("cents")
        if not isinstance(cents, list) or len(cents) != len(zones):
            raise ValueError("a band prices one zone at a time")
        for price in cents:
            if not _whole(price) or price < 0:
                raise ValueError("a price must be a non-negative whole number")
        up_to.append(edge)
        prices.append(cents)
    if up_to[-1] is not None:
        raise ValueError("the book needs one open band")

    extras = book.get("extras")
    if not isinstance(extras, list):
        raise ValueError("the extras must be a list")
    marks = []
    mark_cents = {}
    mark_zones = {}
    for extra in extras:
        if not isinstance(extra, dict):
            raise ValueError("a charge must be a mapping")
        mark = extra.get("mark")
        cents = extra.get("cents")
        covers = extra.get("zones")
        if not isinstance(mark, str) or not mark:
            raise ValueError("a mark must be a non-empty name")
        if mark in mark_cents:
            raise ValueError("a mark is charged twice")
        if not _whole(cents) or cents < 0:
            raise ValueError("a charge must be a non-negative whole number")
        allowed = None
        if covers is not None:
            if not isinstance(covers, list):
                raise ValueError("a charge covers a list of zones")
            allowed = set()
            for zone in covers:
                if not isinstance(zone, str) or zone not in zone_at:
                    raise ValueError("a charge names an unknown zone")
                if zone in allowed:
                    raise ValueError("a charge repeats a zone")
                allowed.add(zone)
        marks.append(mark)
        mark_cents[mark] = cents
        mark_zones[mark] = allowed

    unit = book.get("round")
    if not _whole(unit) or unit <= 0:
        raise ValueError("round must be a positive whole number")

    zone = parcel.get("zone")
    if not isinstance(zone, str) or zone not in zone_at:
        raise ValueError("the parcel names an unknown zone")
    grams = parcel.get("grams")
    if not _whole(grams) or grams <= 0:
        raise ValueError("grams must be a positive whole number")
    carried = parcel.get("marks")
    if not isinstance(carried, list):
        raise ValueError("the parcel's marks must be a list")
    on_parcel = set()
    for mark in carried:
        if not isinstance(mark, str) or mark not in mark_cents:
            raise ValueError("the parcel carries a mark the book does not name")
        if mark in on_parcel:
            raise ValueError("the parcel repeats a mark")
        on_parcel.add(mark)

    band = len(up_to) - 1
    for at, edge in enumerate(up_to):
        if edge is None or grams <= edge:
            band = at
            break
    base = prices[band][zone_at[zone]]
    applied = []
    extra_total = 0
    for mark in marks:
        if mark not in on_parcel:
            continue
        allowed = mark_zones[mark]
        if allowed is not None and zone not in allowed:
            continue
        applied.append(mark)
        extra_total += mark_cents[mark]
    total = base + extra_total
    if total % unit:
        total += unit - (total % unit)
    return {
        "band": band,
        "base": base,
        "extra": extra_total,
        "total": total,
        "applied": applied,
    }
