def group_totals(rows: list[dict], key: str, field: str) -> list[list]:
    if not isinstance(rows, list):
        raise ValueError("group_totals expects a list of rows")
    totals: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict) or key not in row or field not in row:
            raise ValueError("row is missing a required property")
        label = row[key]
        amount = row[field]
        if not isinstance(label, str):
            raise ValueError("group label must be a string")
        if not isinstance(amount, int) or isinstance(amount, bool):
            raise ValueError("amount must be an integer")
        totals[label] = totals.get(label, 0) + amount
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return [[label, total] for label, total in ranked]
