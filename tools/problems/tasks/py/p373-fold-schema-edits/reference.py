def fold_schema_edits(fields: list, edits: list) -> list:
    if not isinstance(fields, list) or len(fields) == 0:
        raise ValueError("the header must be a non-empty list")
    header = []
    for field in fields:
        if not isinstance(field, str) or field == "":
            raise ValueError("every heading must be a non-empty string")
        if field in header:
            raise ValueError("the header repeats " + field)
        header.append(field)
    if not isinstance(edits, list):
        raise ValueError("the edits must be a list")
    for edit in edits:
        if not isinstance(edit, dict):
            raise ValueError("every edit must be a mapping")
        field = edit.get("field")
        if not isinstance(field, str) or field == "":
            raise ValueError("every edit must name a non-empty heading")
        op = edit.get("op")
        if op == "add":
            if field in header:
                raise ValueError(field + " is already taken")
            header.append(field)
        elif op == "drop":
            if field not in header:
                raise ValueError("no heading called " + field)
            header.remove(field)
        elif op == "rename":
            into = edit.get("into")
            if not isinstance(into, str) or into == "":
                raise ValueError("a rename must give a non-empty into")
            if field not in header:
                raise ValueError("no heading called " + field)
            if into in header:
                raise ValueError(into + " is already taken")
            header[header.index(field)] = into
        else:
            raise ValueError("an op must be add, drop or rename")
    return header
