import re


def fill_desk_map(plan: list, legend: dict) -> dict:
    if not isinstance(plan, list) or len(plan) == 0:
        raise ValueError("the floor must be a non-empty list of rows")
    width = -1
    for row in plan:
        if not isinstance(row, str) or row == "":
            raise ValueError("every row must be a non-empty string")
        if width == -1:
            width = len(row)
        elif len(row) != width:
            raise ValueError("the rows are not all the same length")
        for ch in row:
            if ch != "#" and ch != "." and not ("a" <= ch <= "z"):
                raise ValueError("stray character on the floor: " + ch)
    if not isinstance(legend, dict):
        raise ValueError("the legend must be a mapping")

    desks = {}
    for r, row in enumerate(plan):
        for c, ch in enumerate(row):
            if "a" <= ch <= "z":
                desks.setdefault(ch, []).append((r, c))

    grid = [list(row) for row in plan]
    sat = []
    used = set()
    taken = 0

    for label in sorted(legend):
        if not isinstance(label, str) or re.fullmatch(r"[a-z]", label) is None:
            raise ValueError("a bank letter must be exactly one small letter")
        if label not in desks:
            raise ValueError("the floor draws no bank " + label)
        names = legend[label]
        if not isinstance(names, list):
            raise ValueError("bank " + label + " must carry a list of people")
        spots = desks[label]
        if len(names) > len(spots):
            raise ValueError("bank " + label + " has more people than desks")
        for i, name in enumerate(names):
            if not isinstance(name, str) or re.fullmatch(r"[A-Za-z]+", name) is None:
                raise ValueError("a name must be a non-empty string of letters")
            if name in used:
                raise ValueError("one name is handed two desks: " + name)
            used.add(name)
            r, c = spots[i]
            grid[r][c] = name[0].upper()
            sat.append(name + " r" + str(r) + " c" + str(c))
            taken += 1

    total = sum(len(spots) for spots in desks.values())
    return {
        "floor": ["".join(row) for row in grid],
        "sat": sat,
        "spare": total - taken,
    }
