def value_keys(store: dict) -> dict:
    counts = {}
    for value in store.values():
        counts[value] = counts.get(value, 0) + 1
    return counts
