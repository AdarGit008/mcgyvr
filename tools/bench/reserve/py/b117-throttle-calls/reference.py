"""Replay metered calls through a sliding-window throttle."""


def throttle_calls(span, cap, budget, calls):
    if isinstance(span, bool) or not isinstance(span, int) or span <= 0:
        raise ValueError("span must be a positive integer of seconds")
    if isinstance(cap, bool) or not isinstance(cap, int) or cap <= 0:
        raise ValueError("cap must be a positive integer of units")
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
        raise ValueError("budget must be a non-negative integer of units")
    passed = []
    verdicts = []
    remaining = budget
    previous = 0
    for call in calls:
        if not isinstance(call, list) or len(call) != 2:
            raise ValueError("a call is a [time, units] pair")
        time, units = call
        if isinstance(time, bool) or not isinstance(time, int) or time < 0:
            raise ValueError("a call time must be a non-negative integer")
        if isinstance(units, bool) or not isinstance(units, int) or units <= 0:
            raise ValueError("call units must be a positive integer")
        if time < previous:
            raise ValueError("call times must not decrease")
        previous = time
        while passed and passed[0][0] <= time - span:
            passed.pop(0)
        load = units + sum(spent for _, spent in passed)
        if load <= cap and units <= remaining:
            passed.append([time, units])
            remaining -= units
            verdicts.append("pass")
        else:
            verdicts.append("drop")
    return {"verdicts": verdicts, "remaining": remaining}
