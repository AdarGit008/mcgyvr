def bracket_seed_order(count):
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or count < 2
        or count & (count - 1) != 0
    ):
        raise ValueError("count must be a power of two, at least 2")
    sheet = [1]
    size = 1
    while size < count:
        size *= 2
        sheet = [entry for seed in sheet for entry in (seed, size + 1 - seed)]
    return sheet
