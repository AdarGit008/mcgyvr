def bin_rotate(entries: list[str], places: int) -> list[str]:
    if len(entries) == 0:
        return []
    shift = places % len(entries)
    out = []
    for i in range(len(entries)):
        out.append(entries[(i - shift + len(entries)) % len(entries)])
    return out
