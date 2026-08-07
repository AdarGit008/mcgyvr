def _named(value):
    return isinstance(value, str) and value != ""


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def step_drop_report(tallies, order) -> list:
    if not isinstance(order, list) or not order:
        raise ValueError("the order must be a non-empty list")
    wanted = []
    seen = set()
    for step in order:
        if not _named(step):
            raise ValueError("an ordered step must be a non-empty string")
        if step in seen:
            raise ValueError("the order names " + step + " twice")
        seen.add(step)
        wanted.append(step)
    if not isinstance(tallies, list):
        raise ValueError("the tallies must be a list")
    counted = {}
    for tally in tallies:
        if not isinstance(tally, list) or len(tally) != 2:
            raise ValueError("a tally must be a list of exactly two items")
        step, count = tally
        if not _named(step):
            raise ValueError("a step name must be a non-empty string")
        if not _whole(count) or count < 0:
            raise ValueError("a count must be a whole number of zero or more")
        if step not in seen:
            raise ValueError("the order does not name " + step)
        if step in counted:
            raise ValueError(step + " is tallied more than once")
        counted[step] = count
    for step in wanted:
        if step not in counted:
            raise ValueError(step + " has no tally")

    top = counted[wanted[0]]
    report = []
    for index, step in enumerate(wanted):
        count = counted[step]
        if index == 0:
            report.append(
                {
                    "step": step,
                    "count": count,
                    "lost": 0,
                    "share": 0 if top == 0 else 100,
                }
            )
            continue
        above = counted[wanted[index - 1]]
        if count > above:
            raise ValueError(step + " stands above the step over it")
        report.append(
            {
                "step": step,
                "count": count,
                "lost": above - count,
                "share": 0 if top == 0 else (count * 100) // top,
            }
        )
    return report
