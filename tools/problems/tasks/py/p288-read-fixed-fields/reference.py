def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def read_fixed_fields(lines: list[str], layout: list[dict]) -> list[dict]:
    if not isinstance(layout, list) or not layout:
        raise ValueError("layout must be a non-empty list")
    names: set[str] = set()
    claimed: set[int] = set()
    for field in layout:
        if not isinstance(field, dict):
            raise ValueError("a layout entry must be a record")
        name = field.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("a field name must be a non-empty string")
        if name in names:
            raise ValueError(f"field names repeat: {name}")
        names.add(name)
        start = field.get("start")
        if not _whole(start) or start < 1:
            raise ValueError(f"start must be an integer of at least 1: {name}")
        width = field.get("width")
        if not _whole(width) or width < 1:
            raise ValueError(f"width must be an integer of at least 1: {name}")
        for column in range(start, start + width):
            if column in claimed:
                raise ValueError(f"two fields claim column {column}")
            claimed.add(column)

    if not isinstance(lines, list):
        raise ValueError("lines must be a list of strings")
    for line in lines:
        if not isinstance(line, str):
            raise ValueError("lines must be a list of strings")
        if "\t" in line:
            raise ValueError("a tab cannot be measured on a column grid")

    read: list[dict] = []
    for line in lines:
        record: dict = {}
        for field in layout:
            start = field["start"]
            width = field["width"]
            raw = line[start - 1 : start - 1 + width]
            record[field["name"]] = (raw + " " * (width - len(raw))).rstrip(" ")
        read.append(record)
    return read
