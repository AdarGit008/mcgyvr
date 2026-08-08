def _climb(register: dict, start: str) -> dict:
    seen = {start: 0}
    frontier = [start]
    step = 0
    while frontier:
        step += 1
        following = []
        for name in frontier:
            for up in register[name]:
                if up == start:
                    raise ValueError("climbing closes a loop")
                if up not in seen:
                    seen[up] = step
                    following.append(up)
        frontier = following
    return seen


def kinship_degree(register: dict, one: str, other: str) -> dict:
    if not isinstance(register, dict):
        raise ValueError("the register must be a mapping")
    for name, forebears in register.items():
        if not isinstance(name, str) or not name:
            raise ValueError("a key must be a non-empty string")
        if not isinstance(forebears, list):
            raise ValueError("a forebear list must be a list")
        if len(forebears) > 2:
            raise ValueError("nobody has three forebears")
        held = set()
        for up in forebears:
            if not isinstance(up, str) or not up:
                raise ValueError("a forebear must be a non-empty string")
            if up == name:
                raise ValueError("nobody is their own forebear")
            if up in held:
                raise ValueError("a list names the same forebear twice")
            held.add(up)
            if up not in register:
                raise ValueError("a forebear is not a key of the register")
    for name in register:
        _climb(register, name)
    if not isinstance(one, str) or one not in register:
        raise ValueError("the second person is not a key")
    if not isinstance(other, str) or other not in register:
        raise ValueError("the third person is not a key")

    if one == other:
        return {"steps": 0, "line": "direct", "meet": one}
    mine = _climb(register, one)
    theirs = _climb(register, other)
    if other in mine:
        return {"steps": mine[other], "line": "direct", "meet": other}
    if one in theirs:
        return {"steps": theirs[one], "line": "direct", "meet": one}
    meet = ""
    steps = 0
    for name, up in mine.items():
        down = theirs.get(name)
        if down is None:
            continue
        total = up + down
        if meet == "" or total < steps or (total == steps and name < meet):
            meet = name
            steps = total
    if meet == "":
        return {"steps": 0, "line": "apart", "meet": ""}
    return {"steps": steps, "line": "collateral", "meet": meet}
