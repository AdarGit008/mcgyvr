def _group_table() -> list:
    table: list = []
    for first in range(5):
        for second in range(first + 1, 5):
            places = ["f" if place in (first, second) else "t" for place in range(5)]
            table.append("".join(places))
    return table


def read_scanned_bars(sweep: list) -> dict:
    if not isinstance(sweep, list):
        raise ValueError("the sweep is a list of measures")
    if len(sweep) < 9:
        raise ValueError("a strip never sweeps fewer than nine bars")
    for measure in sweep:
        if not isinstance(measure, int) or isinstance(measure, bool) or measure < 1:
            raise ValueError("a measure is a whole number of one or more")
    thin = min(sweep)

    read: list = []
    for measure in sweep:
        if 2 * measure < 3 * thin:
            read.append("t")
        elif 2 * measure > 3 * thin and measure <= 3 * thin:
            read.append("f")
        else:
            raise ValueError(f"a bar measuring {measure} spoils the sweep")
    if read[0] != "t" or read[1] != "t":
        raise ValueError("the opening mark is two thin bars")
    if read[-2] != "f" or read[-1] != "t":
        raise ValueError("the closing mark is a fat bar and a thin bar")
    body = read[2:-2]
    if not body or len(body) % 5 != 0:
        raise ValueError("the bars between the marks do not divide into groups of five")

    table = _group_table()
    digits = ""
    for at in range(0, len(body), 5):
        group = "".join(body[at : at + 5])
        if group not in table:
            raise ValueError("a group carries other than two fat bars")
        digits += str(table.index(group))
    return {"digits": digits, "thin": thin}
