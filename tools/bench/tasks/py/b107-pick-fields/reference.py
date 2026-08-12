def pick_fields(records, fields):
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    if not isinstance(fields, list) or not fields:
        raise ValueError("fields must be a non-empty list")

    wanted = []
    seen = set()
    for field in fields:
        if not isinstance(field, str):
            raise ValueError("field names must be strings")
        optional = field.endswith("?")
        stem = field[:-1] if optional else field
        if not stem:
            raise ValueError("a field name needs at least one character")
        if stem in seen:
            raise ValueError("field " + stem + " is named twice")
        seen.add(stem)
        wanted.append((stem, optional))

    rows = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("every record must be a mapping")
        row = []
        for stem, optional in wanted:
            if stem in record:
                row.append(record[stem])
            elif optional:
                row.append(None)
            else:
                raise ValueError("record is missing field " + stem)
        rows.append(row)
    return rows
