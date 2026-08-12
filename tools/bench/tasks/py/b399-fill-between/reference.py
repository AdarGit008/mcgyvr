def fill_between(entries: list, filler: str) -> list:
    if len(entries) < 2:
        return list(entries)
    out = [entries[0]]
    for entry in entries[1:]:
        out.append(filler)
        out.append(entry)
    return out
