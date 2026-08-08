def _named(value):
    return isinstance(value, str) and value != ""


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def funnel_rung_reach(marks, ladder, window) -> list:
    if not isinstance(ladder, list) or not ladder:
        raise ValueError("the ladder must be a non-empty list")
    rungs = []
    known = set()
    for step in ladder:
        if not _named(step):
            raise ValueError("a ladder step must be a non-empty string")
        if step in known:
            raise ValueError("the ladder names " + step + " twice")
        known.add(step)
        rungs.append(step)
    if not _whole(window) or window < 0:
        raise ValueError("window must be a whole number of zero or more")
    if not isinstance(marks, list):
        raise ValueError("the marks must be a list")

    by_actor = {}
    for mark in marks:
        if not isinstance(mark, list) or len(mark) != 3:
            raise ValueError("a mark must be a list of exactly three items")
        actor, step, at = mark
        if not _named(actor) or not _named(step):
            raise ValueError("an actor and a step must be non-empty strings")
        if not _whole(at):
            raise ValueError("an at must be a whole number")
        if step not in known:
            continue
        by_actor.setdefault(actor, []).append((at, step))

    counts = [0] * len(rungs)
    for own in by_actor.values():
        listed = sorted(own, key=lambda one: one[0])
        reached = -1
        for start, (opened, step) in enumerate(listed):
            if step != rungs[0]:
                continue
            held = opened
            depth = 0
            for rung in range(1, len(rungs)):
                found = None
                for at, name in listed:
                    if at > held and name == rungs[rung]:
                        found = at
                        break
                if found is None:
                    break
                if found - opened > window:
                    break
                held = found
                depth = rung
            if depth > reached:
                reached = depth
        for rung in range(reached + 1):
            counts[rung] += 1
    return [[step, counts[index]] for index, step in enumerate(rungs)]
