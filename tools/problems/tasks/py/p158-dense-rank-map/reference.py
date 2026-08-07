def dense_rank_map(values: list, order: str) -> list:
    if order not in ("asc", "desc"):
        raise ValueError("bad order word")
    if not isinstance(values, list) or not values:
        raise ValueError("empty value list")
    for v in values:
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("non-integer value")
    distinct = sorted(set(values), reverse=(order == "desc"))
    rank_of = {v: i + 1 for i, v in enumerate(distinct)}
    return [rank_of[v] for v in values]
