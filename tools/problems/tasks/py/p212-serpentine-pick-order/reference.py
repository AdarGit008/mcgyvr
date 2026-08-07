def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def serpentine_pick_order(picks: object) -> list:
    if not isinstance(picks, list):
        raise ValueError("the pick list must be a list")
    seen = set()
    rows = []
    for at, pick in enumerate(picks):
        if not isinstance(pick, dict):
            raise ValueError("a pick must be a mapping")
        sku = pick.get("sku")
        if not isinstance(sku, str) or not sku:
            raise ValueError("a sku must be a non-empty string")
        if sku in seen:
            raise ValueError("two picks share a sku")
        seen.add(sku)
        aisle = pick.get("aisle")
        bay = pick.get("bay")
        if not _whole(aisle) or aisle < 1:
            raise ValueError("an aisle must be a positive whole number")
        if not _whole(bay) or bay < 1:
            raise ValueError("a bay must be a positive whole number")
        rows.append((aisle, bay if aisle % 2 == 1 else -bay, at, sku))
    rows.sort(key=lambda row: (row[0], row[1], row[2]))
    return [row[3] for row in rows]
