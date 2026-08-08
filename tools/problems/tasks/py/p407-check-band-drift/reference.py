NEARNESS = {"A": 0, "B": 1, "C": 2}


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def check_band_drift(entries: list, marks: list) -> dict:
    if not isinstance(entries, list) or not entries:
        raise ValueError("the audit needs at least one entry")
    seen = set()
    held = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("an entry must be a record")
        code = entry.get("code")
        if not isinstance(code, str) or code == "":
            raise ValueError("a code must be a non-empty string")
        if code in seen:
            raise ValueError("code {} appears twice".format(code))
        seen.add(code)
        hits = entry.get("hits")
        if not _whole(hits) or hits < 0:
            raise ValueError("hits must be a whole number of nothing or more")
        was = entry.get("was")
        if was not in NEARNESS:
            raise ValueError("the former class must be A, B or C")
        held.append((code, hits, was))
    if not isinstance(marks, list) or len(marks) != 2:
        raise ValueError("the marks must be two whole permille values")
    first, second = marks
    for mark in (first, second):
        if not _whole(mark) or mark < 1 or mark > 999:
            raise ValueError("a mark must be a whole number from 1 to 999")
    if first >= second:
        raise ValueError("the first mark must fall under the second")
    grand = sum(hits for _code, hits, _was in held)
    if grand == 0:
        raise ValueError("the season recorded no hits at all")
    sweep = sorted(held, key=lambda row: (-row[1], row[0]))
    up = []
    down = []
    steady = 0
    piled = 0
    for code, hits, was in sweep:
        piled += hits
        weighed = piled * 1000
        if weighed <= first * grand:
            now = "A"
        elif weighed <= second * grand:
            now = "B"
        else:
            now = "C"
        if NEARNESS[now] < NEARNESS[was]:
            up.append(code)
        elif NEARNESS[now] > NEARNESS[was]:
            down.append(code)
        else:
            steady += 1
    return {"up": up, "down": down, "steady": steady}
