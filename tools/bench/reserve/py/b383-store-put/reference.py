def put_one(store: dict, key: str, value: str) -> dict:
    if key == "":
        raise ValueError("a key must be named")
    out = dict(store)
    out[key] = value
    return out


def put_all(store: dict, pairs: list) -> dict:
    """Several keys set at once, the given store left untouched."""
    out = store
    for key, value in pairs:
        out = put_one(out, key, value)
    return out
