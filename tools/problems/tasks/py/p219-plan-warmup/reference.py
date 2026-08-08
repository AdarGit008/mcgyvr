def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def plan_warmup(brief: dict) -> dict:
    if not isinstance(brief, dict):
        raise ValueError("the brief must be a mapping")
    budget = brief.get("budget")
    slots = brief.get("slots")
    caps = brief.get("caps")
    items = brief.get("items")
    if not _whole(budget) or budget < 0:
        raise ValueError("budget must be a non-negative whole number")
    if not _whole(slots) or slots < 1:
        raise ValueError("slots must be a positive whole number")
    if not isinstance(caps, dict):
        raise ValueError("caps must be a mapping")
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    allowance = {}
    for family, cap in caps.items():
        if not _whole(cap) or cap < 0:
            raise ValueError("a cap must be a non-negative whole number")
        allowance[family] = cap

    names = set()
    lined = []
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("an item must be a mapping")
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("a name must be a non-empty string")
        if name in names:
            raise ValueError("two items share a name")
        names.add(name)
        size = raw.get("bytes")
        weight = raw.get("weight")
        family = raw.get("family")
        if not _whole(size) or size < 1:
            raise ValueError("bytes must be a positive whole number")
        if not _whole(weight) or weight < 0:
            raise ValueError("weight must be a non-negative whole number")
        if not isinstance(family, str) or not family:
            raise ValueError("a family must be a non-empty string")
        if family not in allowance:
            raise ValueError("caps does not mention a family an item belongs to")
        lined.append((name, size, weight, family))

    lined.sort(key=lambda row: (-row[2], row[1], row[0]))

    spent = {}
    loaded = []
    turned = []
    places = slots
    spare = budget
    for name, size, _weight, family in lined:
        used = spent.get(family, 0)
        if places == 0:
            turned.append({"name": name, "why": "slots"})
        elif used >= allowance[family]:
            turned.append({"name": name, "why": "family"})
        elif size > spare:
            turned.append({"name": name, "why": "bytes"})
        else:
            places -= 1
            spent[family] = used + 1
            spare -= size
            loaded.append(name)
    return {"loaded": loaded, "spare": spare, "turned": turned}
