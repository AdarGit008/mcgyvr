def stitch_tables(left: list, right: list, key: str, mode: str) -> list:
    if mode not in ("inner", "left"):
        raise ValueError("unknown mode")

    def key_of(row):
        value = row.get(key)
        if not isinstance(value, str):
            raise ValueError("every record needs the key column as a string")
        return value

    by_key = {}
    right_cols = set()
    for row in right:
        value = key_of(row)
        if value in by_key:
            raise ValueError("a right-table key value repeats")
        by_key[value] = row
        right_cols.update(name for name in row if name != key)

    left_keys = []
    left_cols = set()
    for row in left:
        left_keys.append(key_of(row))
        left_cols.update(name for name in row if name != key)

    shared = right_cols & left_cols
    if shared:
        raise ValueError("the tables share a non-key column: " + sorted(shared)[0])

    stitched = []
    for row, value in zip(left, left_keys):
        partner = by_key.get(value)
        if partner is None and mode == "inner":
            continue
        merged = dict(row)
        if partner is None:
            for name in right_cols:
                merged[name] = None
        else:
            for name, item in partner.items():
                if name != key:
                    merged[name] = item
        stitched.append(merged)
    return stitched
