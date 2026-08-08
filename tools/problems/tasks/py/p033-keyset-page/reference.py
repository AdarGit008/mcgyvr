def keyset_page(ids: list[int], cursor: int, limit: int) -> dict:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer")
    if not isinstance(cursor, int) or isinstance(cursor, bool):
        raise ValueError("cursor must be an integer")
    if not isinstance(ids, list) or any(
        not isinstance(v, int) or isinstance(v, bool) for v in ids
    ):
        raise ValueError("ids must be a list of integers")
    for previous, current in zip(ids, ids[1:]):
        if current <= previous:
            raise ValueError("ids must be strictly increasing")
    beyond = [v for v in ids if v > cursor]
    return {"items": beyond[:limit], "done": len(beyond) <= limit}
