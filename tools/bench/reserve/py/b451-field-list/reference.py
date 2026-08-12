def field_or(record: dict, field: str, stand_in: str) -> str:
    return record[field] if field in record else stand_in


def field_list(records: list, field: str, stand_in: str) -> list:
    return [field_or(record, field, stand_in) for record in records]
