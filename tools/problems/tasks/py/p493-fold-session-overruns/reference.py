def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def fold_session_overruns(runsheet: list, wall: int) -> dict:
    if not _whole(wall) or wall < 1:
        raise ValueError("the wall is not whole or falls below one")
    if not isinstance(runsheet, list):
        raise ValueError("fold_session_overruns expects a list of entries")

    named = set()
    for entry in runsheet:
        if not isinstance(entry, dict):
            raise ValueError("an entry is not a record")
        if sorted(entry) != ["pause", "ran", "slot", "speaker"]:
            raise ValueError("an entry's keys are not exactly the four named")
        speaker = entry["speaker"]
        if not isinstance(speaker, str) or not speaker:
            raise ValueError("a speaker is not a non-empty string")
        if speaker in named:
            raise ValueError("two entries name one speaker")
        named.add(speaker)
        if not _whole(entry["slot"]) or entry["slot"] < 1:
            raise ValueError("a slot is not whole or falls below one")
        if not _whole(entry["ran"]) or entry["ran"] < 0:
            raise ValueError("a ran is not whole or falls below nought")
        if not _whole(entry["pause"]) or entry["pause"] < 0:
            raise ValueError("a pause is not whole or falls below nought")

    lines = []
    spill = []
    clock = 0
    finish = 0

    for entry in runsheet:
        speaker = entry["speaker"]
        ran = entry["ran"]
        slot = entry["slot"]
        pause = entry["pause"]

        if clock >= wall:
            spill.append(speaker)
            continue
        start = clock
        end = start + ran
        mark = "full"
        if end > wall:
            end = wall
            mark = "cut"
        lines.append(f"{speaker} {start} {end} {mark}")
        finish = end
        beyond = ran - slot if ran > slot else 0
        clock = end + max(0, pause - beyond)

    return {"lines": lines, "spill": spill, "finish": finish}
