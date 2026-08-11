def held_down(value: int, ceiling: int) -> int:
    return ceiling if value > ceiling else value


def limit_map(store: dict, ceiling: int) -> dict:
    """Every value of a store brought down to a ceiling."""
    out = {}
    for key, value in store.items():
        out[key] = held_down(value, ceiling)
    return out
