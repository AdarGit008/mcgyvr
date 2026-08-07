def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def slide_sessions(sessions: list, opens_at: int, closes_at: int) -> list:
    if not _whole(opens_at) or not _whole(closes_at):
        raise ValueError("the day's bounds must be integers")
    if opens_at >= closes_at:
        raise ValueError("the studio must close after it opens")
    seen = set()
    for row in sessions:
        if not isinstance(row, dict):
            raise ValueError("each request must be a record")
        if not isinstance(row.get("id"), str) or row["id"] == "":
            raise ValueError("id must be a non-empty string")
        if not _whole(row.get("want")):
            raise ValueError("want must be an integer")
        if not _whole(row.get("span")) or row["span"] < 1:
            raise ValueError("span must be a positive integer")
        if row["id"] in seen:
            raise ValueError("repeated request id: " + row["id"])
        seen.add(row["id"])

    placed = []
    booked = []
    for row in sessions:
        earliest = max(row["want"], opens_at)
        tries = {earliest}
        for span in placed:
            if span[1] >= earliest:
                tries.add(span[1])
        granted = None
        for moment in sorted(tries):
            if moment + row["span"] > closes_at:
                break
            clash = any(
                moment < span[1] and span[0] < moment + row["span"]
                for span in placed
            )
            if not clash:
                granted = moment
                break
        if granted is None:
            booked.append(row["id"] + " away")
        else:
            placed.append((granted, granted + row["span"]))
            booked.append(row["id"] + " " + str(granted))
    return booked
