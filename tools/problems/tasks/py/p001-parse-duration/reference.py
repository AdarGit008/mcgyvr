import re


def parse_duration(text: str) -> int:
    if not isinstance(text, str):
        raise ValueError("parse_duration expects a string")
    if re.fullmatch(r"(?:\d+[dhms])+", text) is None:
        raise ValueError("malformed duration")
    seconds = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    rank = "dhms"
    units = []
    total = 0
    for value, unit in re.findall(r"(\d+)([dhms])", text):
        units.append(unit)
        total += int(value) * seconds[unit]
    for previous, current in zip(units, units[1:]):
        if rank.index(current) <= rank.index(previous):
            raise ValueError("units out of order or repeated")
    return total
