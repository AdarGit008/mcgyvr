def toggle_range(value: int, lo: int, hi: int) -> int:
    for argument in (value, lo, hi):
        if not isinstance(argument, int) or isinstance(argument, bool):
            raise ValueError("toggle_range expects integer arguments")
    if value < 0 or value >= 2**30:
        raise ValueError("value must be within 0..2**30-1")
    if lo < 0 or hi > 29:
        raise ValueError("bit positions must be within 0..29")
    if lo > hi:
        raise ValueError("lo must not exceed hi")
    mask = ((1 << (hi - lo + 1)) - 1) << lo
    return value ^ mask
