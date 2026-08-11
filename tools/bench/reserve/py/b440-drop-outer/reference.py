def drop_outer(entries: list) -> list:
    if len(entries) <= 2:
        return []
    return entries[1:-1]
