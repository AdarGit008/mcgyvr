PERIOD_CEILING = 100000


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _read_pair(record):
    if not isinstance(record, (list, tuple)) or len(record) != 2:
        raise ValueError("every record must be a pair")
    key, period = record[0], record[1]
    if not isinstance(key, str) or key == "":
        raise ValueError("a key must be a non-empty string")
    if not _whole(period) or period < 0 or period > PERIOD_CEILING:
        raise ValueError("a period must be a whole number from 0 through 100000")
    return key, period


def cohort_hold_grid(members: list, sightings: list, horizon: int) -> list:
    if not isinstance(members, list):
        raise ValueError("members must be a list")
    if not isinstance(sightings, list):
        raise ValueError("sightings must be a list")
    if not _whole(horizon) or horizon < 0 or horizon > 50:
        raise ValueError("horizon must be a whole number from 0 through 50")

    intake = {}
    for record in members:
        key, period = _read_pair(record)
        if key in intake:
            raise ValueError(f"member {key} is logged twice")
        intake[key] = period

    alive = {}
    for record in sightings:
        key, period = _read_pair(record)
        if key not in intake:
            raise ValueError(f"sighting names unlogged member {key}")
        if period < intake[key]:
            raise ValueError(f"sighting for {key} stands before its intake")
        alive.setdefault(key, set()).add(period)

    groups = {}
    for key, period in intake.items():
        groups.setdefault(period, []).append(key)

    rows = []
    for period in sorted(groups):
        keys = groups[period]
        row = [period, len(keys)]
        for offset in range(horizon + 1):
            tally = 0
            for key in keys:
                if period + offset in alive.get(key, ()):
                    tally += 1
            row.append(tally)
        rows.append(row)
    return rows
