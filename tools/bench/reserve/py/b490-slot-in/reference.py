def slot_in(ordered: list[int], value: int) -> list[int]:
    out = []
    placed = False
    for item in ordered:
        if not placed and value < item:
            out.append(value)
            placed = True
        out.append(item)
    if not placed:
        out.append(value)
    return out
