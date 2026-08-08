from itertools import product


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def build_set_meal(courses: list, quarrels: list) -> dict:
    if not isinstance(courses, list) or not courses:
        raise ValueError("a set meal needs at least one course")
    if len(courses) > 6:
        raise ValueError("more than six courses is too many")
    if not isinstance(quarrels, list):
        raise ValueError("the quarrels must be a list of pairs")

    offered = set()
    for course in courses:
        if not isinstance(course, list) or not course:
            raise ValueError("a course must offer at least one option")
        if len(course) > 6:
            raise ValueError("a course may not offer more than six options")
        for option in course:
            if not isinstance(option, dict):
                raise ValueError("each option must be a record")
            code = option.get("code")
            if not isinstance(code, str) or code == "":
                raise ValueError("a code must be a non-empty string")
            if code in offered:
                raise ValueError("the code " + code + " is offered twice")
            offered.add(code)
            price = option.get("price")
            if not _whole(price) or price < 1:
                raise ValueError("a price must be a whole number of pence, one or more")

    pairs = []
    for quarrel in quarrels:
        if not isinstance(quarrel, list) or len(quarrel) != 2:
            raise ValueError("a quarrel must be a pair of codes")
        left, right = quarrel
        if left not in offered or right not in offered:
            raise ValueError("a quarrel names a code no course offers")
        if left == right:
            raise ValueError("a quarrel writes the code " + left + " twice")
        pairs.append((left, right))

    best = None
    for choice in product(*[range(len(course)) for course in courses]):
        picks = [courses[i][k]["code"] for i, k in enumerate(choice)]
        total = sum(courses[i][k]["price"] for i, k in enumerate(choice))
        chosen = set(picks)
        if any(left in chosen and right in chosen for left, right in pairs):
            continue
        key = (total, picks)
        if best is None or key < best:
            best = key

    if best is None:
        raise ValueError("no tray avoids every quarrel")
    return {"total": best[0], "picks": best[1]}
