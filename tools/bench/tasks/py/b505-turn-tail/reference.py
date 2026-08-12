def turn_tail(entries: list[str], count: int) -> list[str]:
    out = []
    start = len(entries) - count
    if start < 0:
        start = 0
    for i in range(start):
        out.append(entries[i])
    for i in range(len(entries) - 1, start - 1, -1):
        out.append(entries[i])
    return out
