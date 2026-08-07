import re

_MM = {"mm": 1, "cm": 10, "m": 1000, "km": 1000000}


def convert_length(quantity: str, goal: str) -> int:
    if not isinstance(quantity, str) or not isinstance(goal, str):
        raise ValueError("expected strings")
    if goal not in _MM:
        raise ValueError("unknown target symbol")
    if quantity == "":
        raise ValueError("empty quantity")
    total_mm = 0
    for part in quantity.split(" "):
        match = re.fullmatch(r"(\d+)(mm|cm|m|km)", part)
        if match is None:
            raise ValueError("malformed part")
        total_mm += int(match.group(1)) * _MM[match.group(2)]
    if total_mm % _MM[goal] != 0:
        raise ValueError("does not divide evenly into the target")
    return total_mm // _MM[goal]
