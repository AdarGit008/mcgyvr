def count_by(records: list, field: str) -> dict:
    if field == "":
        raise ValueError("a field must be named")
    counts = {}
    for record in records:
        if field in record:
            counts[record[field]] = counts.get(record[field], 0) + 1
    return counts
