def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def prune_archive_budget(files: list, budget: int, limit: int, least: int) -> dict:
    if not isinstance(files, list):
        raise ValueError("the archive must be a list of files")
    if not _whole(budget) or budget < 0:
        raise ValueError("the budget must be a whole number of nothing or more")
    if not _whole(limit) or limit < 1:
        raise ValueError("the age limit must be a whole number above nothing")
    if not _whole(least) or least < 0:
        raise ValueError("the least number must be a whole number of nothing or more")
    seen = set()
    standing = []
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError("a file must be a record")
        label = entry.get("label")
        if not isinstance(label, str) or label == "":
            raise ValueError("a label must be a non-empty string")
        if label in seen:
            raise ValueError("label {} appears twice".format(label))
        seen.add(label)
        size = entry.get("size")
        age = entry.get("age")
        if not _whole(size) or size < 0:
            raise ValueError("a size must be a whole number of nothing or more")
        if not _whole(age) or age < 0:
            raise ValueError("an age must be a whole number of nothing or more")
        standing.append((label, size, age))
    removed = []
    while len(standing) > least:
        weight = sum(size for _label, size, _age in standing)
        stale = sum(1 for _label, _size, age in standing if age > limit)
        if stale == 0 and weight <= budget:
            break
        doomed = standing[0]
        for entry in standing:
            if (-entry[2], -entry[1], entry[0]) < (-doomed[2], -doomed[1], doomed[0]):
                doomed = entry
        removed.append(doomed[0])
        standing = [entry for entry in standing if entry[0] != doomed[0]]
    held = sum(size for _label, size, _age in standing)
    stale = sum(1 for _label, _size, age in standing if age > limit)
    return {
        "removed": removed,
        "held": held,
        "over": held - budget if held > budget else 0,
        "stale": stale,
    }
