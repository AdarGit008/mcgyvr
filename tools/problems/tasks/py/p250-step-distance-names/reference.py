TABLE = [
    "unison",
    "minor second",
    "major second",
    "minor third",
    "major third",
    "perfect fourth",
    "tritone",
    "perfect fifth",
    "minor sixth",
    "major sixth",
    "minor seventh",
    "major seventh",
]
SWEET = {0, 3, 4, 5, 7, 8, 9}


def name_step_distances(steps: list) -> dict:
    if not isinstance(steps, list) or not steps:
        raise ValueError("the argument must be a list holding at least one step")
    names = []
    lifts = []
    colours = []
    tally = {}
    widest = 0
    greatest = -1
    for at, step in enumerate(steps):
        if not isinstance(step, list) or len(step) != 2:
            raise ValueError("a step must be a list of exactly two pitch marks")
        for mark in step:
            if not isinstance(mark, int) or isinstance(mark, bool):
                raise ValueError("a pitch mark must be a whole number")
        reach = abs(step[0] - step[1])
        lift = reach // 12
        leftover = reach % 12
        name = TABLE[leftover]
        names.append(name)
        lifts.append(lift)
        colours.append("sweet" if leftover in SWEET else "sharp")
        tally[name] = tally.get(name, 0) + 1
        if reach > greatest:
            greatest = reach
            widest = at
    return {
        "names": names,
        "lifts": lifts,
        "colours": colours,
        "tally": tally,
        "widest": widest,
    }
