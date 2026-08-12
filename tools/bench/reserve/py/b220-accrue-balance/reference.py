"""Grow a whole-cent balance, carrying the sub-cent interest between periods."""


def accrue_balance(opening: int, rate: int, periods: int) -> int:
    if isinstance(rate, bool) or not isinstance(rate, int) or rate < 0:
        raise ValueError("rate must be a whole number of basis points of at least 0")
    if isinstance(periods, bool) or not isinstance(periods, int) or periods < 0:
        raise ValueError("periods must be a whole number of at least 0")
    scale = 10000
    total = opening
    carry = 0
    for _ in range(periods):
        carry += total * rate
        cents = carry // scale
        total += cents
        carry -= cents * scale
    if carry * 2 > scale or (carry * 2 == scale and total % 2 == 1):
        total += 1
    return total
