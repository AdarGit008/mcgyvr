def _read_lines(value, what):
    if not isinstance(value, list):
        raise ValueError("the " + what + " must be a list of strings")
    for line in value:
        if not isinstance(line, str):
            raise ValueError("the " + what + " must be a list of strings")
    return list(value)


def apply_patch_hunks(lines: list, hunks: list) -> dict:
    file = _read_lines(lines, "file")
    if not isinstance(hunks, list):
        raise ValueError("the hunks must be a list")
    parsed = []
    for hunk in hunks:
        if not isinstance(hunk, dict):
            raise ValueError("every hunk must be a mapping")
        at = hunk.get("at")
        if not isinstance(at, int) or isinstance(at, bool) or at < 1:
            raise ValueError("at must be a whole number of one or more")
        parsed.append(
            {
                "at": at,
                "before": _read_lines(hunk.get("before"), "before"),
                "after": _read_lines(hunk.get("after"), "after"),
            }
        )
    for earlier, later in zip(parsed, parsed[1:]):
        if later["at"] <= earlier["at"]:
            raise ValueError("the ats must climb strictly")
        if earlier["at"] + len(earlier["before"]) > later["at"]:
            raise ValueError("one hunk reaches into the next")

    out = []
    conflicts = []
    cursor = 0
    for position, hunk in enumerate(parsed):
        start = hunk["at"] - 1
        reach = start + len(hunk["before"])
        clashes = start > len(file) or reach > len(file)
        if not clashes:
            for step, wanted in enumerate(hunk["before"]):
                if file[start + step] != wanted:
                    clashes = True
                    break
        stop = min(start, len(file))
        while cursor < stop:
            out.append(file[cursor])
            cursor += 1
        if clashes:
            conflicts.append(position)
            continue
        cursor = reach
        out.extend(hunk["after"])
    while cursor < len(file):
        out.append(file[cursor])
        cursor += 1
    return {"lines": out, "conflicts": conflicts}
