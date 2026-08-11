import re

FACTORS = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}


def parse_byte_size(text):
    if not isinstance(text, str) or not text:
        raise ValueError("parse_byte_size expects a non-empty string")
    match = re.fullmatch(r"(\d+)([A-Za-z]+)", text)
    if match is None:
        raise ValueError("malformed size: %s" % text)
    count, unit = match.groups()
    if unit not in FACTORS:
        raise ValueError("unknown unit: %s" % unit)
    return int(count) * FACTORS[unit]
