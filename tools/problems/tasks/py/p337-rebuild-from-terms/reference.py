SWELL_LIMIT = 1000000000


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def rebuild_from_terms(run: list) -> list:
    if not isinstance(run, list):
        raise ValueError("the run must be a list")
    if len(run) == 0:
        raise ValueError("an empty run spells no quotient")
    if len(run) > 64:
        raise ValueError("a run may hold at most 64 entries")
    for index, entry in enumerate(run):
        if not _whole(entry):
            raise ValueError("every entry must be a whole number")
        if index == 0:
            if abs(entry) > 1000000:
                raise ValueError("the leading entry is too large")
        elif entry < 1 or entry > 1000:
            raise ValueError("an entry behind the leading one must lie in 1..1000")
    if len(run) > 1 and run[-1] == 1:
        raise ValueError("a run of more than one entry may not end in 1")

    top_before, top_latest = 0, 1
    bottom_before, bottom_latest = 1, 0
    for entry in run:
        top = entry * top_latest + top_before
        bottom = entry * bottom_latest + bottom_before
        if abs(top) > SWELL_LIMIT or abs(bottom) > SWELL_LIMIT:
            raise ValueError("the quotient swells past the limit")
        top_before, top_latest = top_latest, top
        bottom_before, bottom_latest = bottom_latest, bottom
    return [top_latest, bottom_latest]
