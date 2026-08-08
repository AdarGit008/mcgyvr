def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def trim_pocket_overflow(owed: list[int], ceiling: int) -> list[int]:
    if not _whole(ceiling) or ceiling < 0:
        raise ValueError("ceiling must be a whole number of cents, not below zero")
    handed: list[int] = []
    tab = 0
    for entry in owed:
        if not _whole(entry) or entry < 0:
            raise ValueError("every entry must be a whole number of cents, not below zero")
        paid = min(entry, ceiling - tab)
        handed.append(paid)
        tab += paid
    return handed
