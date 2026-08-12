def field_mean(records: list, field: str) -> int:
    values = [record[field] for record in records if field in record]
    if not values:
        return 0
    return sum(values) // len(values)
