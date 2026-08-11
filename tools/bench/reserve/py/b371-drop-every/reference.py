def keep_index(place: int, every: int) -> bool:
    return place % every != 0


def drop_every(entries: list, every: int) -> list:
    kept = []
    for i, entry in enumerate(entries):
        if keep_index(i + 1, every):
            kept.append(entry)
    return kept
