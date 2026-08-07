import re

DOTS = re.compile(r"^[1-6]+$")


def _weight_of(cell: str) -> int:
    if DOTS.match(cell) is None:
        raise ValueError("a cell must be 0 or a run of the digits 1 to 6")
    for i in range(1, len(cell)):
        if cell[i] == cell[i - 1]:
            raise ValueError("a cell may not name a dot twice")
        if cell[i] < cell[i - 1]:
            raise ValueError("the dots of a cell must rise")
    return sum(1 << (int(dot) - 1) for dot in cell)


def read_dot_cells(cells: str) -> str:
    if not isinstance(cells, str):
        raise ValueError("the argument must be a string")
    if len(cells) == 0:
        raise ValueError("the argument must not be empty")
    parts = cells.split("-")
    out = ""
    counting = False
    i = 0
    while i < len(parts):
        cell = parts[i]
        if cell == "0":
            out += " "
            counting = False
            i += 1
            continue
        weight = _weight_of(cell)
        if counting:
            if weight < 1 or weight > 10:
                raise ValueError("a cell inside a count may not weigh more than 10")
            out += str(weight % 10)
            i += 1
            continue
        if weight == 48:
            counting = True
            i += 1
            continue
        if weight == 32:
            if i + 1 >= len(parts):
                raise ValueError("a shift sign may not end the line")
            following = parts[i + 1]
            if following == "0":
                raise ValueError("a shift sign must be followed by a letter")
            letter = _weight_of(following)
            if letter < 1 or letter > 26:
                raise ValueError("a shift sign must be followed by a letter")
            out += chr(64 + letter)
            i += 2
            continue
        if weight < 1 or weight > 26:
            raise ValueError("this weight spells nothing")
        out += chr(96 + weight)
        i += 1
    return out
