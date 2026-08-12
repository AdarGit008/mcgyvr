def pick_max(records: list, field: str) -> dict:
    best = None
    for record in records:
        if field not in record:
            continue
        if best is None or record[field] > best[field]:
            best = record
    return {} if best is None else best
