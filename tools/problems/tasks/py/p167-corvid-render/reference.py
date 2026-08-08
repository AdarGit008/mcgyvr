MARKS = "vwxyz"


def corvid_render(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("corvid_render expects a whole number")
    if value == 0:
        return "x"
    rest = value
    marks = []
    while rest != 0:
        lean = rest % 5
        if lean > 2:
            lean -= 5
        marks.append(MARKS[lean + 2])
        rest = (rest - lean) // 5
    marks.reverse()
    return "".join(marks)
