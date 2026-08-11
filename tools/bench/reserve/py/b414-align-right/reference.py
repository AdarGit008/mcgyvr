def widest_of(entries: list) -> int:
    widest = 0
    for entry in entries:
        if len(entry) > widest:
            widest = len(entry)
    return widest


def align_right(entries: list) -> list:
    width = widest_of(entries)
    out = []
    for entry in entries:
        out.append(" " * (width - len(entry)) + entry)
    return out
