def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_rounds(row):
    return row == list(range(1, len(row) + 1))


def _shapely(row, bells):
    return len(row) == bells and sorted(row) == list(range(1, bells + 1))


def _neighbourly(before, row):
    seat = 0
    while seat < len(before):
        if before[seat] == row[seat]:
            seat += 1
            continue
        if (
            seat + 1 < len(before)
            and before[seat] == row[seat + 1]
            and before[seat + 1] == row[seat]
        ):
            seat += 2
            continue
        return False
    return True


def audit_ringing_line(rows: list) -> dict:
    if not isinstance(rows, list) or len(rows) == 0:
        raise ValueError("audit_ringing_line expects a non-empty list of rows")
    for row in rows:
        if not isinstance(row, list):
            raise ValueError("a row is not a list")
        for bell in row:
            if not _whole(bell):
                raise ValueError("a row entry is not whole")
    bells = len(rows[0])
    if bells < 2:
        raise ValueError("the opening row holds fewer than two bells")
    if not _is_rounds(rows[0]):
        raise ValueError("the opening row is not rounds")

    rung = {tuple(rows[0])}
    for seat in range(1, len(rows)):
        row = rows[seat]
        if not _shapely(row, bells):
            return {"ok": False, "fault": "shape", "row": seat + 1}
        if not _neighbourly(rows[seat - 1], row):
            return {"ok": False, "fault": "jump", "row": seat + 1}
        mark = tuple(row)
        if mark in rung and not (_is_rounds(row) and seat == len(rows) - 1):
            return {"ok": False, "fault": "repeat", "row": seat + 1}
        rung.add(mark)
    return {"ok": True, "fault": "", "row": 0}
