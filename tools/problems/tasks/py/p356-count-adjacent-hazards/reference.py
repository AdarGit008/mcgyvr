TOUCHING = [
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
]


def count_adjacent_hazards(field: list) -> dict:
    if not isinstance(field, list):
        raise ValueError("the field must be a list of rows")
    if len(field) == 0:
        raise ValueError("the field must hold at least one row")
    width = None
    for row in field:
        if not isinstance(row, str):
            raise ValueError("every row must be a string")
        if len(row) == 0:
            raise ValueError("a row must not be empty")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise ValueError("the rows are not all the same length")
        for symbol in row:
            if symbol not in ("#", "."):
                raise ValueError("a symbol is neither a hash nor a dot")
    height = len(field)
    chart = []
    hazards = 0
    clear = 0
    for down in range(height):
        drawn = []
        for across in range(width):
            if field[down][across] == "#":
                hazards += 1
                drawn.append("#")
                continue
            clear += 1
            tally = 0
            for step_down, step_across in TOUCHING:
                near_down = down + step_down
                near_across = across + step_across
                if 0 <= near_down < height and 0 <= near_across < width:
                    if field[near_down][near_across] == "#":
                        tally += 1
            drawn.append(str(tally))
        chart.append("".join(drawn))
    return {"chart": chart, "hazards": hazards, "clear": clear}
