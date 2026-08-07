import re


def plotter_pose(program):
    if not isinstance(program, str):
        raise ValueError("the program must be a string")
    if re.fullmatch(r"(?:F\d+|B\d+|L|R)*", program) is None:
        raise ValueError("malformed program")
    headings = ["N", "E", "S", "W"]
    deltas = {"N": (0, 1), "E": (1, 0), "S": (0, -1), "W": (-1, 0)}
    heading = 0
    x = 0
    y = 0
    for drive, digits, spin in re.findall(r"([FB])(\d+)|([LR])", program):
        if spin == "L":
            heading = (heading + 3) % 4
        elif spin == "R":
            heading = (heading + 1) % 4
        else:
            distance = int(digits)
            if distance == 0:
                raise ValueError("a drive distance of zero is malformed")
            sign = 1 if drive == "F" else -1
            dx, dy = deltas[headings[heading]]
            x += sign * distance * dx
            y += sign * distance * dy
    return {"x": x, "y": y, "facing": headings[heading]}
