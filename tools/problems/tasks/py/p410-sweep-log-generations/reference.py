import re

PLAIN_NUMBER = re.compile(r"[1-9][0-9]*")


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def sweep_log_generations(base: str, files: list, rules: dict) -> dict:
    if not isinstance(base, str) or base == "":
        raise ValueError("the live name must be a non-empty string")
    if not isinstance(files, list):
        raise ValueError("the files must be a list")
    if not isinstance(rules, dict):
        raise ValueError("the rules must be a record")
    rotate_at = rules.get("rotateAt")
    keep = rules.get("keep")
    max_days = rules.get("maxDays")
    for setting in (rotate_at, keep, max_days):
        if not _whole(setting) or setting < 1:
            raise ValueError("each rule must be a whole number above nothing")
    seen = set()
    copies = {}
    live_bytes = -1
    live_days = -1
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError("a file must be a record")
        name = entry.get("name")
        if not isinstance(name, str):
            raise ValueError("a name must be a string")
        if name in seen:
            raise ValueError("name {} appears twice".format(name))
        seen.add(name)
        size = entry.get("bytes")
        days = entry.get("days")
        if not _whole(size) or size < 0:
            raise ValueError("bytes must be a whole number of nothing or more")
        if not _whole(days) or days < 0:
            raise ValueError("days must be a whole number of nothing or more")
        if name == base:
            live_bytes = size
            live_days = days
            continue
        if not name.startswith(base + "."):
            raise ValueError("name {} belongs to no generation here".format(name))
        suffix = name[len(base) + 1 :]
        if PLAIN_NUMBER.fullmatch(suffix) is None:
            raise ValueError("copy number {} is not written plainly".format(suffix))
        copies[int(suffix)] = days
    if live_bytes < 0:
        raise ValueError("the live file is missing")
    for number in range(1, len(copies) + 1):
        if number not in copies:
            raise ValueError("copy number {} is missing".format(number))
    rotated = []
    placed = {}
    if live_bytes >= rotate_at:
        placed[1] = live_days
        rotated.append([base, base + ".1"])
        for number in range(1, len(copies) + 1):
            placed[number + 1] = copies[number]
            rotated.append([base + "." + str(number), base + "." + str(number + 1)])
    else:
        for number in range(1, len(copies) + 1):
            placed[number] = copies[number]
    kept = [base]
    deleted = []
    for number in range(1, len(placed) + 1):
        name = base + "." + str(number)
        if number > keep or placed[number] > max_days:
            deleted.append(name)
        else:
            kept.append(name)
    return {"kept": kept, "rotated": rotated, "deleted": deleted}
