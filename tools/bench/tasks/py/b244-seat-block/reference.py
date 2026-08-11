import re


def seat_block(label: str) -> list:
    found = re.fullmatch(r"(\d+)([A-Z])", label)
    if found is None:
        raise ValueError("not a seat label: " + label)
    return [int(found.group(1)), found.group(2)]
