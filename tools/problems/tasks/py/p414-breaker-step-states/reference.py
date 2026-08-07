def _counting(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def trace_breaker_states(outcomes: list, settings: dict) -> list:
    if not isinstance(outcomes, list):
        raise ValueError("outcomes must be a list")
    for outcome in outcomes:
        if outcome not in ("pass", "fail"):
            raise ValueError("an outcome is either pass or fail")
    if not isinstance(settings, dict):
        raise ValueError("settings must be a record")
    for key in ("trip", "cool", "proof"):
        if key not in settings:
            raise ValueError("settings is missing " + key)
        if not _counting(settings[key]):
            raise ValueError(key + " must be a whole number of one or more")
    trip = settings["trip"]
    cool = settings["cool"]
    proof = settings["proof"]
    posture = "closed"
    losing = 0
    winning = 0
    countdown = 0
    trace = []
    for outcome in outcomes:
        if posture == "closed":
            losing = losing + 1 if outcome == "fail" else 0
            if losing == trip:
                posture = "open"
                countdown = cool
        elif posture == "open":
            countdown -= 1
            if countdown == 0:
                posture = "half"
                winning = 0
        else:
            if outcome == "pass":
                winning += 1
                if winning == proof:
                    posture = "closed"
                    losing = 0
            else:
                posture = "open"
                countdown = cool
        trace.append(posture)
    return trace
