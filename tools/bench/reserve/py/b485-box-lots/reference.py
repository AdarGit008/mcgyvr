def box_lots(entries: list[str], size: int) -> list[list[str]]:
    packed = []
    lot = []
    for entry in entries:
        lot.append(entry)
        if len(lot) == size:
            packed.append(lot)
            lot = []
    if len(lot) > 0:
        packed.append(lot)
    return packed
