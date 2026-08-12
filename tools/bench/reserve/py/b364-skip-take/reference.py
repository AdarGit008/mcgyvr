def skip_take(entries: list, take: int, skip: int) -> list:
    kept = []
    i = 0
    while i < len(entries) and take > 0:
        kept.extend(entries[i : i + take])
        i += take + skip
    return kept
