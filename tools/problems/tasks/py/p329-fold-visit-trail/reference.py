def _marked(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _handled(value):
    return isinstance(value, str) and value != ""


def fold_visit_trail(pings, idle) -> list:
    if not isinstance(pings, list):
        raise ValueError("the pings must be a list")
    if not _marked(idle) or idle < 1:
        raise ValueError("idle must be a whole number of one or more")
    trails = {}
    for ping in pings:
        if not isinstance(ping, list) or len(ping) != 2:
            raise ValueError("a ping must be a list of exactly two items")
        handle, stamp = ping
        if not _handled(handle):
            raise ValueError("a handle must be a non-empty string")
        if not _marked(stamp):
            raise ValueError("a stamp must be a whole number")
        stamps = trails.setdefault(handle, [])
        if stamp in stamps:
            raise ValueError("a handle carries one stamp twice")
        stamps.append(stamp)
    folded = []
    for handle in sorted(trails):
        stamps = sorted(trails[handle])
        runs = []
        for index, stamp in enumerate(stamps):
            if index == 0 or stamp - stamps[index - 1] >= idle:
                runs.append(1)
            else:
                runs[-1] += 1
        folded.append([handle, runs])
    return folded
