def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _read_lines(lines):
    if not isinstance(lines, list) or not lines:
        raise ValueError("the line list must hold at least one line")
    seen = set()
    held = []
    for line in lines:
        if not isinstance(line, dict):
            raise ValueError("a line must be a record")
        code = line.get("code")
        if not isinstance(code, str) or code == "":
            raise ValueError("a code must be a non-empty string")
        if code in seen:
            raise ValueError("code {} appears twice".format(code))
        seen.add(code)
        picks = line.get("picks")
        if not _whole(picks) or picks < 0:
            raise ValueError("picks must be a whole number of nothing or more")
        held.append((code, picks))
    return held


def _read_rows(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("the row list must hold at least one row")
    seen = set()
    shelves = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("a row must be a record")
        code = row.get("code")
        if not isinstance(code, str) or code == "":
            raise ValueError("a row code must be a non-empty string")
        if code in seen:
            raise ValueError("row code {} appears twice".format(code))
        seen.add(code)
        capacity = row.get("capacity")
        if not _whole(capacity) or capacity < 1:
            raise ValueError("a capacity must be a whole number above nothing")
        shelves.append((code, capacity))
    return shelves


def band_picks_by_share(lines: list, cuts: list, rows: list) -> list:
    held = _read_lines(lines)
    if not isinstance(cuts, list) or len(cuts) != 2:
        raise ValueError("the cuts must be two whole percentages")
    first, second = cuts
    for cut in (first, second):
        if not _whole(cut) or cut < 1 or cut > 99:
            raise ValueError("a cut must be a whole number from 1 to 99")
    if first >= second:
        raise ValueError("the first cut must fall below the second")
    shelves = _read_rows(rows)
    grand = sum(picks for _code, picks in held)
    if grand == 0:
        raise ValueError("no line was pulled at all")
    ranked = sorted(held, key=lambda pair: (-pair[1], pair[0]))
    banded = []
    running = 0
    for code, picks in ranked:
        if running * 100 < first * grand:
            band = "A"
        elif running * 100 < second * grand:
            band = "B"
        else:
            band = "C"
        banded.append((code, band))
        running += picks
    seated = []
    row_index = 0
    slot = 0
    for band in ("A", "B", "C"):
        members = [code for code, letter in banded if letter == band]
        if not members:
            continue
        if slot > 0:
            row_index += 1
            slot = 0
        for code in members:
            while row_index < len(shelves) and slot == shelves[row_index][1]:
                row_index += 1
                slot = 0
            if row_index >= len(shelves):
                raise ValueError("the rows run out before every line is seated")
            slot += 1
            seated.append(
                {
                    "code": code,
                    "band": band,
                    "row": shelves[row_index][0],
                    "slot": slot,
                }
            )
    return seated
