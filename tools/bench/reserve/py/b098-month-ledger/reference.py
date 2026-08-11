import re


def month_ledger(entries: list) -> list:
    if not isinstance(entries, list):
        raise ValueError("entries must be a list")
    minutes_by = {}
    count_by = {}
    for stamp, minutes in entries:
        if not isinstance(stamp, str):
            raise ValueError("a day stamp must be a string")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp) is None:
            raise ValueError("malformed day stamp")
        month = int(stamp[5:7])
        if month < 1 or month > 12:
            raise ValueError("month out of range: " + stamp)
        day = int(stamp[8:10])
        if day < 1 or day > 31:
            raise ValueError("day out of range: " + stamp)
        if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes <= 0:
            raise ValueError("minutes must be a positive integer")
        key = stamp[:7]
        minutes_by[key] = minutes_by.get(key, 0) + minutes
        count_by[key] = count_by.get(key, 0) + 1
    return [[key, minutes_by[key], count_by[key]] for key in sorted(minutes_by)]
