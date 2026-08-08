STAY_CAP = 20160


def _whole(value, low, high, what):
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(what + " must be a whole number")
    if value < low or (high is not None and value > high):
        raise ValueError(what + " lies outside its allowed range")
    return value


def tiered_parking_charge(tariff: dict, ticket: dict) -> dict:
    if not isinstance(tariff, dict) or not isinstance(ticket, dict):
        raise ValueError("the tariff and the ticket must both be mappings")
    raw_tiers = tariff.get("tiers")
    if not isinstance(raw_tiers, list) or len(raw_tiers) == 0:
        raise ValueError("the tiers must be a non-empty list")
    tiers = []
    opens = 0
    previous = 0
    for position, tier in enumerate(raw_tiers):
        if not isinstance(tier, dict):
            raise ValueError("every tier must be a mapping")
        up_to = tier.get("upTo")
        if up_to is None:
            opens += 1
            if position != len(raw_tiers) - 1:
                raise ValueError("the open tier must come last")
        else:
            _whole(up_to, 1, None, "a tier's stated minutes")
            if up_to <= previous:
                raise ValueError("the stated minutes must climb strictly")
            previous = up_to
        rate = tier.get("rate")
        _whole(rate, 0, None, "a tier's rate")
        tiers.append({"upTo": up_to, "rate": rate})
    if opens != 1:
        raise ValueError("there must be exactly one open tier")

    cap = tariff.get("cap")
    if cap is not None:
        _whole(cap, 0, None, "the cap")
    day_start = _whole(tariff.get("dayStart"), 0, 1439, "dayStart")
    grace = _whole(tariff.get("grace"), 0, None, "the grace")
    entry = _whole(ticket.get("entry"), 0, None, "entry")
    stay = _whole(ticket.get("stay"), 1, STAY_CAP, "the stay")

    if stay <= grace:
        return {"days": [], "capped": [], "cents": 0}

    leaves = entry + stay - 1
    first = (entry - day_start) // 1440
    last = (leaves - day_start) // 1440
    days = []
    capped = []
    total = 0
    for number in range(first, last + 1):
        opened = day_start + number * 1440
        from_minute = max(entry, opened)
        to_minute = min(leaves, opened + 1439)
        minutes = to_minute - from_minute + 1
        charge = 0
        done = 0
        for tier in tiers:
            if done >= minutes:
                break
            reach = minutes if tier["upTo"] is None else min(tier["upTo"], minutes)
            take = reach - done
            if take > 0:
                charge += take * tier["rate"]
                done += take
        if cap is not None and charge > cap:
            charge = cap
            capped.append(len(days))
        days.append(charge)
        total += charge
    return {"days": days, "capped": capped, "cents": total}
