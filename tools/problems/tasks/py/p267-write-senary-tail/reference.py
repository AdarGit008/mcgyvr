def whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def write_senary_tail(numerator: int, denominator: int) -> str:
    if not whole(numerator) or not whole(denominator):
        raise ValueError("both readings must be whole numbers")
    if denominator < 1 or denominator > 10000:
        raise ValueError("the lower reading must lie in 1..10000")
    if numerator < 0 or numerator >= denominator:
        raise ValueError(
            "the upper reading must sit at or above zero and below the lower one"
        )
    if numerator == 0:
        return "0"
    seen = {}
    marks = []
    carry = numerator
    opens = -1
    while carry != 0:
        if carry in seen:
            opens = seen[carry]
            break
        seen[carry] = len(marks)
        lifted = carry * 6
        marks.append(str(lifted // denominator))
        carry = lifted % denominator
    if opens == -1:
        return "".join(marks)
    return "".join(marks[:opens]) + "|" + "".join(marks[opens:]) + "|"
