def over_count(store: dict, floor: int) -> int:
    """How many of a store's values reach a floor."""
    found = 0
    for value in store.values():
        if value >= floor:
            found += 1
    return found
