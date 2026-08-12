def spill_lots(lots: list[list[str]]) -> list[str]:
    out = []
    for lot in lots:
        for entry in lot:
            if len(entry) > 0:
                out.append(entry)
    return out
