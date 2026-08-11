"""Read a grouped decimal amount as a whole number of cents."""

import re

SHAPE = re.compile(r"(-?)(\d+|\d{1,3}(?:,\d{3})+)(?:\.(\d{1,2}))?")


def cents_of(amount: str) -> int:
    if not isinstance(amount, str):
        raise ValueError("cents_of expects a string")
    found = SHAPE.fullmatch(amount)
    if found is None:
        raise ValueError("amount does not read as an amount: " + amount)
    sign, whole, decimals = found.groups()
    units = int(whole.replace(",", ""))
    cents = 0
    if decimals is not None:
        cents = int(decimals if len(decimals) == 2 else decimals + "0")
    total = units * 100 + cents
    return -total if sign == "-" else total
