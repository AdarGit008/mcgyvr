import re


def shift_lane_label(label: str, step: int) -> str:
    if not isinstance(label, str):
        raise ValueError("a lane label is a string")
    if len(label) == 0:
        raise ValueError("a lane label needs at least one capital")
    if len(label) > 3:
        raise ValueError("the board stops at three capitals")
    if re.fullmatch(r"[A-Z]+", label) is None:
        raise ValueError("a lane label carries capitals only")
    if isinstance(step, bool) or not isinstance(step, int):
        raise ValueError("the step must be a whole number")
    place = 0
    for capital in label:
        place = place * 26 + (ord(capital) - 64)
    target = place + step
    if target < 1 or target > 18278:
        raise ValueError("that step walks off the board")
    lettered = ""
    left = target
    while left > 0:
        rest = (left - 1) % 26
        lettered = chr(65 + rest) + lettered
        left = (left - 1) // 26
    return lettered
