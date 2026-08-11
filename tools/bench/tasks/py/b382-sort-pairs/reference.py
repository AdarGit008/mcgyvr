def field_of(record: dict, field: str) -> int:
    if field not in record:
        raise ValueError("the record lacks that field")
    return record[field]


def sort_pairs(records: list, field: str) -> list:
    return sorted(records, key=lambda record: field_of(record, field))
