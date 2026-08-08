def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def plan_archive_index(entries: list, total: int) -> dict:
    if not isinstance(entries, list):
        raise ValueError("entries must be a list")
    if not _whole(total) or total < 0:
        raise ValueError("total must be a whole number of nought or more")

    named: set[str] = set()
    slots: list[tuple[int, int, str]] = []
    for entry in entries:
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            raise ValueError("an entry is a [name, offset, length] triple")
        name, offset, length = entry
        if not isinstance(name, str) or not name:
            raise ValueError("a name must be a non-empty string")
        if name in named:
            raise ValueError(f"two entries carry the name {name}")
        named.add(name)
        if not _whole(offset) or offset < 0:
            raise ValueError("an offset must be a whole number of nought or more")
        if not _whole(length) or length < 0:
            raise ValueError("a length must be a whole number of nought or more")
        slots.append((offset, length, name))

    slots.sort()
    order = [slot[2] for slot in slots]

    for offset, length, name in slots:
        if offset + length > total:
            return {"fault": "truncated", "blame": [name], "order": order, "gaps": [], "slack": 0, "used": 0}

    held = [slot for slot in slots if slot[1] > 0]
    for earlier, later in zip(held, held[1:]):
        if earlier[0] + earlier[1] > later[0]:
            return {
                "fault": "overlap",
                "blame": [earlier[2], later[2]],
                "order": order,
                "gaps": [],
                "slack": 0,
                "used": 0,
            }

    gaps: list[list[int]] = []
    cursor = 0
    used = 0
    for offset, length, _name in held:
        if offset > cursor:
            gaps.append([cursor, offset - cursor])
        cursor = offset + length
        used += length
    return {"fault": "", "blame": [], "order": order, "gaps": gaps, "slack": total - cursor, "used": used}
