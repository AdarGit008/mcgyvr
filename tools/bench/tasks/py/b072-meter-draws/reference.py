def remaining_for(used, key, allowance):
    return allowance - used.get(key, 0)


def meter_draws(draws, allowance):
    if isinstance(allowance, bool) or not isinstance(allowance, int) or allowance <= 0:
        raise ValueError("allowance must be a positive integer")
    used = {}
    denied = []
    for index, draw in enumerate(draws):
        key, units = draw
        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")
        if isinstance(units, bool) or not isinstance(units, int) or units <= 0:
            raise ValueError("units must be a positive integer")
        used.setdefault(key, 0)
        if units <= remaining_for(used, key, allowance):
            used[key] += units
        else:
            denied.append(index)
    return {"used": used, "denied": denied}
