"""Cent-exact money helpers for order totals."""


def split_evenly(total_cents: int, ways: int) -> list:
    if (
        isinstance(total_cents, bool)
        or not isinstance(total_cents, int)
        or total_cents < 0
    ):
        raise ValueError("total must be a non-negative integer of cents")
    if isinstance(ways, bool) or not isinstance(ways, int) or ways <= 0:
        raise ValueError("ways must be a positive integer")
    base = total_cents // ways
    extra = total_cents - base * ways
    return [base + 1 if i < extra else base for i in range(ways)]


def apply_bps(cents: int, bps: int) -> int:
    if isinstance(cents, bool) or not isinstance(cents, int) or cents < 0:
        raise ValueError("cents must be a non-negative integer")
    if isinstance(bps, bool) or not isinstance(bps, int) or bps < 0:
        raise ValueError("bps must be a non-negative integer")
    return (cents * bps + 5000) // 10000


def sum_parts(parts: list) -> int:
    total = 0
    for part in parts:
        if isinstance(part, bool) or not isinstance(part, int):
            raise ValueError("parts must be integers")
        total += part
    return total
