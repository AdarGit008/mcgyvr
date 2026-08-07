def _is_whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _code_set(codes: list, where: str) -> set:
    seen: set = set()
    for code in codes:
        if not isinstance(code, str) or code == "":
            raise ValueError("every car code is a non-empty string")
        if code in seen:
            raise ValueError(f"{where} writes the code {code} twice")
        seen.add(code)
    return seen


def plan_shunting(arrival: list, target: list, depth: int) -> dict:
    if not isinstance(arrival, list) or not isinstance(target, list):
        raise ValueError("plan_shunting expects two lists of car codes")
    if not arrival:
        raise ValueError("the arrival road holds no cars")
    standing = _code_set(arrival, "the arrival road")
    wanted = _code_set(target, "the departure order")
    if wanted != standing:
        raise ValueError("the two lists do not name the same cars")
    if not _is_whole(depth) or depth < 1:
        raise ValueError("the siding depth is a whole number of one or more")

    moves: list = []
    siding: list = []
    pulled = 0
    want = 0
    while want < len(target):
        top = siding[-1] if siding else None
        if top is not None and top == target[want]:
            siding.pop()
            moves.append("place " + top)
            want += 1
            continue
        if pulled >= len(arrival):
            return {"moves": moves, "blocked": "buried:" + target[want]}
        if len(siding) >= depth:
            return {"moves": moves, "blocked": "full"}
        siding.append(arrival[pulled])
        moves.append("hold " + arrival[pulled])
        pulled += 1
    return {"moves": moves, "blocked": ""}
