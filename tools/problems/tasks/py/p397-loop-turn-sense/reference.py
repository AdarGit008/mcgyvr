def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def loop_turn_sense(studs: list) -> dict:
    if not isinstance(studs, list):
        raise ValueError("loop_turn_sense expects a list of studs")
    if len(studs) < 3:
        raise ValueError("a loop carries at least three studs")
    loop = []
    seen = set()
    for stud in studs:
        if (
            not isinstance(stud, list)
            or len(stud) != 2
            or not _whole(stud[0])
            or not _whole(stud[1])
        ):
            raise ValueError("a stud must be a pair of two whole numbers")
        if abs(stud[0]) > 10000 or abs(stud[1]) > 10000:
            raise ValueError("a measure magnitude passes ten thousand")
        key = (stud[0], stud[1])
        if key in seen:
            raise ValueError("a stud shows up more than once")
        seen.add(key)
        loop.append([stud[0], stud[1]])
    sweep = 0
    for index, here in enumerate(loop):
        following = loop[(index + 1) % len(loop)]
        sweep += here[0] * following[1] - following[0] * here[1]
    if sweep > 0:
        sense = "counter"
    elif sweep < 0:
        sense = "clockwise"
    else:
        sense = "flat"
    return {"doubled": abs(sweep), "sense": sense}
