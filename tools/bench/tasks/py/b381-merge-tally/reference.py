def add_one(tally: dict, name: str, amount: int) -> dict:
    merged = dict(tally)
    merged[name] = merged.get(name, 0) + amount
    return merged


def merge_tally(left: dict, right: dict) -> dict:
    merged = dict(left)
    for name, amount in right.items():
        merged = add_one(merged, name, amount)
    return merged
