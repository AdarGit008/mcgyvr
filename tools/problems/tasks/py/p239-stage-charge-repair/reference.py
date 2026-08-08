CODES = {"done", "soft", "hard"}


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def charge_stages(stages: list, forgive: int) -> list:
    if not _whole(forgive) or forgive < 0:
        raise ValueError("forgive must be a whole number of zero or more")
    if not isinstance(stages, list):
        raise ValueError("the pipeline must be a list of stage records")
    seen = set()
    for stage in stages:
        if not isinstance(stage, dict):
            raise ValueError("each stage must be a record")
        name = stage.get("name")
        if not isinstance(name, str) or name == "":
            raise ValueError("a stage name must be a non-empty string")
        if name in seen:
            raise ValueError("repeated stage name: " + name)
        seen.add(name)
        tries = stage.get("tries")
        if not isinstance(tries, list) or not tries:
            raise ValueError(name + " ran no attempts")
        for index, attempt in enumerate(tries):
            if not isinstance(attempt, dict):
                raise ValueError("each attempt must be a record")
            if not _whole(attempt.get("secs")) or attempt["secs"] < 0:
                raise ValueError("secs must be a whole number of zero or more")
            if attempt.get("code") not in CODES:
                raise ValueError("unknown attempt code in " + name)
            if index > 0 and tries[index - 1]["code"] != "soft":
                raise ValueError(name + " ran on after it had finished")

    bills = []
    for stage in stages:
        wall = 0
        billed = 0
        softs = 0
        for attempt in stage["tries"]:
            wall += attempt["secs"]
            if attempt["code"] == "soft":
                softs += 1
                if softs > forgive:
                    billed += attempt["secs"]
            else:
                billed += attempt["secs"]
        bills.append(
            {
                "name": stage["name"],
                "wall": wall,
                "billed": billed,
                "free": wall - billed,
            }
        )
    return bills
