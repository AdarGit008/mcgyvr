def bin_spill(bins: dict, limit: int) -> list:
    return [name for name, held in bins.items() if held > limit]


def bin_add(bins: dict, name: str, count: int) -> dict:
    updated = dict(bins)
    updated[name] = updated.get(name, 0) + count
    return updated
