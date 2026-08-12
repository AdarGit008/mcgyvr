def split_at(entries: list, marker: str) -> list:
    for i, entry in enumerate(entries):
        if entry == marker:
            return [entries[:i], entries[i + 1 :]]
    return [list(entries), []]
