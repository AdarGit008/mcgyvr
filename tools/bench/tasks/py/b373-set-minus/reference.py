def set_minus(entries: list, remove: list) -> list:
    unwanted = set(remove)
    kept = []
    for entry in entries:
        if entry not in unwanted:
            kept.append(entry)
    return kept
