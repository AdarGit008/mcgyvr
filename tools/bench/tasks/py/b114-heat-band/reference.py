def run_thermostat(start, low, high, power, drifts):
    for bound in (start, low, high):
        if isinstance(bound, bool) or not isinstance(bound, int):
            raise ValueError("temperatures must be integers")
    if low >= high:
        raise ValueError("low must lie strictly below high")
    if isinstance(power, bool) or not isinstance(power, int) or power <= 0:
        raise ValueError("power must be a positive integer")
    if not isinstance(drifts, list):
        raise ValueError("drifts must be a list")
    temp = start
    heating = False
    heated = 0
    switches = 0
    coldest = start
    for drift in drifts:
        if isinstance(drift, bool) or not isinstance(drift, int):
            raise ValueError("drifts must be integers")
        if temp < low and not heating:
            heating = True
            switches += 1
        elif temp >= high and heating:
            heating = False
            switches += 1
        if heating:
            heated += 1
            temp += power
        temp += drift
        coldest = min(coldest, temp)
    return {
        "temp": temp,
        "heated": heated,
        "switches": switches,
        "coldest": coldest,
    }
