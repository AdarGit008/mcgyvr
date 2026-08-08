def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def flag_probe_readings(readings: object, rules: object) -> list[list[str]]:
    if not isinstance(readings, list) or not readings:
        raise ValueError("readings must be a non-empty list")
    for reading in readings:
        if not _whole(reading):
            raise ValueError("every reading must be a whole number")
    if not isinstance(rules, dict):
        raise ValueError("rules must be a mapping")
    for key in ("low", "high", "jump", "stuck"):
        if not _whole(rules.get(key)):
            raise ValueError(f"{key} must be a whole number")
    low = rules["low"]
    high = rules["high"]
    jump = rules["jump"]
    stuck = rules["stuck"]
    if low > high:
        raise ValueError("low must not sit above high")
    if jump < 0:
        raise ValueError("jump must not be beneath zero")
    if stuck < 2:
        raise ValueError("stuck must not be beneath two")

    report: list[list[str]] = []
    reference: int | None = None
    run_value = readings[0]
    run_length = 0
    for reading in readings:
        if reading == run_value:
            run_length += 1
        else:
            run_value = reading
            run_length = 1
        flags: list[str] = []
        implausible = reading < low or reading > high
        if implausible:
            flags.append("range")
        elif reference is not None and abs(reading - reference) > jump:
            flags.append("jump")
        if run_length >= stuck:
            flags.append("stuck")
        if not implausible:
            reference = reading
        report.append(flags)
    return report
