def row_keys(row: dict) -> list:
    return list(row.keys())


def merge_rows(under: dict, over: dict) -> dict:
    """One row laid over another, the row above winning."""
    merged = dict(under)
    for key in row_keys(over):
        merged[key] = over[key]
    return merged
