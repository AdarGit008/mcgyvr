CAPITALS = "ABCDEFG"


def marlow_step(rungs: str, lift: int) -> str:
    if not isinstance(rungs, str):
        raise ValueError("marlow_step expects the rung-count as text")
    if len(rungs) == 0:
        raise ValueError("a rung-count is never empty")
    if len(rungs) > 10:
        raise ValueError("a rung-count runs no longer than ten capitals")
    for mark in rungs:
        if mark not in CAPITALS:
            raise ValueError("a rung-count carries only the capitals A through G")
    if len(rungs) > 1 and rungs[0] == "A":
        raise ValueError("a rung-count of two or more never begins with A")
    if not isinstance(lift, int) or isinstance(lift, bool):
        raise ValueError("lift must be a whole number")
    if abs(lift) > 1000:
        raise ValueError("lift's magnitude passes one thousand")
    quantity = 0
    for mark in rungs:
        quantity = quantity * -7 + CAPITALS.index(mark)
    quantity += lift
    if quantity == 0:
        return "A"
    rest = quantity
    record = ""
    while rest != 0:
        column = rest % 7
        record = CAPITALS[column] + record
        rest = (rest - column) // -7
    return record
