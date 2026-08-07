"""How deep a strip of fitted prints runs."""


def _whole(value, least):
    return isinstance(value, int) and not isinstance(value, bool) and value >= least


def lay_shot_shelves(shots: list, strip: dict) -> dict:
    if not isinstance(shots, list) or len(shots) == 0:
        raise ValueError("shots must be a list holding at least one shot")
    if not isinstance(strip, dict):
        raise ValueError("strip must be a record")
    per_row = strip.get("per_row")
    cell = strip.get("cell")
    lead = strip.get("lead")
    if not _whole(per_row, 1):
        raise ValueError("per_row must be a whole number above nought")
    if not _whole(cell, 1):
        raise ValueError("cell must be a whole number above nought")
    if not _whole(lead, 0):
        raise ValueError("lead must be a whole number of nought or more")

    seen = set()
    fitted = []
    for shot in shots:
        if not isinstance(shot, dict):
            raise ValueError("each shot must be a record")
        name = shot.get("name")
        if not isinstance(name, str) or name == "":
            raise ValueError("name must be a non-empty string")
        if name in seen:
            raise ValueError(f"two shots answer to the name {name}")
        seen.add(name)
        if not _whole(shot.get("across"), 1) or not _whole(shot.get("down"), 1):
            raise ValueError("across and down must be whole numbers above nought")
        across = shot["across"]
        fitted.append((name, -((-shot["down"] * cell) // across)))

    rows = []
    for start in range(0, len(fitted), per_row):
        chunk = fitted[start : start + per_row]
        rows.append(
            {
                "names": [name for name, _ in chunk],
                "deep": max(deep for _, deep in chunk),
            }
        )
    total = sum(row["deep"] for row in rows) + lead * (len(rows) - 1)
    return {"rows": rows, "deep": total}
