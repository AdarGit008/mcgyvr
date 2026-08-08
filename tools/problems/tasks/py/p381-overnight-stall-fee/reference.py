MINUTE_CAP = 10080


def _whole(value, low, high, what):
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(what + " must be a whole number")
    if value < low or (high is not None and value > high):
        raise ValueError(what + " lies outside its allowed range")
    return value


def overnight_stall_fee(entry: int, minutes: int, sheet: dict) -> dict:
    if not isinstance(sheet, dict):
        raise ValueError("the fee sheet must be a mapping")
    first_hour = _whole(sheet.get("firstHour"), 0, None, "firstHour")
    later_hour = _whole(sheet.get("laterHour"), 0, None, "laterHour")
    day_cap = _whole(sheet.get("dayCap"), 0, None, "dayCap")
    night_fee = _whole(sheet.get("nightFee"), 0, None, "nightFee")
    arrives = _whole(entry, 0, None, "entry")
    stood = _whole(minutes, 1, MINUTE_CAP, "minutes")

    leaves = arrives + stood - 1
    days = []
    nights = 0
    total = 0
    for number in range(arrives // 1440, leaves // 1440 + 1):
        opened = number * 1440
        from_minute = max(arrives, opened)
        to_minute = min(leaves, opened + 1439)
        held = to_minute - from_minute + 1
        hours = (held + 59) // 60
        charge = first_hour + (hours - 1) * later_hour
        if charge > day_cap:
            charge = day_cap
        if from_minute - opened < 300 and to_minute - opened >= 60:
            charge += night_fee
            nights += 1
        days.append(charge)
        total += charge
    return {"days": days, "nights": nights, "total": total}
