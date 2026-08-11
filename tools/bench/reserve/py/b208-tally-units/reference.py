"""Total each item in base units and report it in the largest exact unit."""


def tally_by_unit(entries: list, units: dict) -> dict:
    totals = {}
    for item, count, unit in entries:
        base = count * units[unit]
        totals[item] = totals.get(item, 0) + base

    ladder = sorted(units.items(), key=lambda pair: -pair[1])
    report = {}
    for item, total in totals.items():
        for name, worth in ladder:
            if total % worth == 0:
                report[item] = (total // worth, name)
                break
    return report
