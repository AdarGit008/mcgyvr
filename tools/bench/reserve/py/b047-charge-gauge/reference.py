"""Battery gauge readings for a millivolt-calibrated pack."""


def charge_percent(mv, empty_mv, full_mv):
    for value in (mv, empty_mv, full_mv):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("millivolt values must be integers")
    if empty_mv >= full_mv:
        raise ValueError("empty bound must lie below full bound")
    if mv <= empty_mv:
        return 0
    if mv >= full_mv:
        return 100
    span = full_mv - empty_mv
    return ((mv - empty_mv) * 200 + span) // (2 * span)


def band_label(percent):
    if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
        raise ValueError("percent must be an integer from 0 to 100")
    if percent < 15:
        return "low"
    return "ok" if percent < 85 else "full"
