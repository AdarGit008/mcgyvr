def has_all(store: dict, needed: list) -> bool:
    for key in needed:
        if key not in store:
            return False
    return True
