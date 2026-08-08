def draw_branch_lanes(entries: list) -> list:
    if not isinstance(entries, list) or not entries:
        raise ValueError("there must be at least one entry to draw")
    seen_ids = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("every entry must be a mapping")
        for field in ("id", "branch"):
            held = entry.get(field)
            if not isinstance(held, str) or not held:
                raise ValueError(f"every entry needs a non-empty {field}")
        if entry["id"] in seen_ids:
            raise ValueError("two entries share the id " + entry["id"])
        seen_ids.add(entry["id"])

    last_row = {}
    for row, entry in enumerate(entries):
        last_row[entry["branch"]] = row

    lanes = {}
    rows = []
    for row, entry in enumerate(entries):
        branch = entry["branch"]
        if branch not in lanes:
            taken = set(lanes.values())
            lane = 0
            while lane in taken:
                lane += 1
            lanes[branch] = lane
        own = lanes[branch]
        held = set(lanes.values())
        marks = []
        for lane in range(max(held) + 1):
            if lane == own:
                marks.append("*")
            elif lane in held:
                marks.append("|")
            else:
                marks.append(" ")
        rows.append(" ".join(marks) + " " + entry["id"])
        if last_row[branch] == row:
            del lanes[branch]
    return rows
