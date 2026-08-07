def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def plan_room_moves(bookings: list) -> list:
    if not isinstance(bookings, list):
        raise ValueError("plan_room_moves expects a list of bookings")
    seen = set()
    for row in bookings:
        if not isinstance(row, dict):
            raise ValueError("each booking must be a record")
        ident = row.get("id")
        start = row.get("start")
        end = row.get("end")
        fixed = row.get("fixed")
        if not isinstance(ident, str) or ident == "":
            raise ValueError("id must be a non-empty string")
        if not _whole(start) or not _whole(end):
            raise ValueError("start and end must be integers")
        if start >= end:
            raise ValueError("start must come strictly before end")
        if not isinstance(fixed, bool):
            raise ValueError("fixed must be a boolean")
        if ident in seen:
            raise ValueError("repeated booking id: " + ident)
        seen.add(ident)

    nailed = sorted(
        (row for row in bookings if row["fixed"]),
        key=lambda row: (row["start"], row["end"]),
    )
    for earlier, later in zip(nailed, nailed[1:]):
        if later["start"] < earlier["end"]:
            raise ValueError("two fixed bookings overlap and cannot be repaired")

    moved = []
    loose = []
    for row in bookings:
        if row["fixed"]:
            continue
        clashes = any(
            row["start"] < nail["end"] and nail["start"] < row["end"]
            for nail in nailed
        )
        if clashes:
            moved.append(row)
        else:
            loose.append(row)

    loose.sort(key=lambda row: (row["end"], row["start"], row["id"]))
    kept = set()
    last = None
    for row in loose:
        if last is None or row["start"] >= last:
            kept.add(row["id"])
            last = row["end"]
    moved.extend(row for row in loose if row["id"] not in kept)

    moved.sort(key=lambda row: (row["start"], row["id"]))
    return [row["id"] for row in moved]
