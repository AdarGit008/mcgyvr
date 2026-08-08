def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def join_ledger_cards(cards: list[str], layout: list[dict]) -> list[dict]:
    if not isinstance(layout, list) or not layout:
        raise ValueError("layout must be a non-empty list")
    names: set[str] = set()
    claimed: set[int] = set()
    span = 0
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
        span = max(span, start + width - 1)

    if not isinstance(cards, list) or not cards:
        raise ValueError("cards must be a non-empty list")
    for card in cards:
        if not isinstance(card, str):
            raise ValueError("cards must be a list of strings")
        if card[:1] not in ("=", "+"):
            raise ValueError("a card marker must be = or +")
        if len(card) - 1 < span:
            raise ValueError(f"a card body stops short of column {span}")
    if cards[0][0] != "=":
        raise ValueError("the first card must open a record")

    records: list[dict] = []
    for card in cards:
        values: dict = {}
        for field in layout:
            start = field["start"]
            width = field["width"]
            values[field["name"]] = card[start : start + width].rstrip(".")
        if card[0] == "+":
            open_record = records[-1]
            for field in layout:
                open_record[field["name"]] += values[field["name"]]
            continue
        records.append(values)
    return records
