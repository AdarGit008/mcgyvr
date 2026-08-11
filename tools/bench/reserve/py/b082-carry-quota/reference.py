"""Bill a metered plan's per-period overage under capped carry-over."""


def bill_overage(allowance, carry_cap, usage):
    if not isinstance(allowance, int) or allowance < 0:
        raise ValueError("allowance must be a non-negative integer")
    if not isinstance(carry_cap, int) or carry_cap < 0:
        raise ValueError("carry cap must be a non-negative integer")
    if not isinstance(usage, list):
        raise ValueError("usage must be a list")
    billed = []
    carried = 0
    for used in usage:
        if not isinstance(used, int) or used < 0:
            raise ValueError("each period's usage must be a non-negative integer")
        available = allowance + carried
        if used > available:
            billed.append(used - available)
            carried = 0
        else:
            billed.append(0)
            carried = min(carry_cap, available - used)
    return {"billed": billed, "carried": carried}
