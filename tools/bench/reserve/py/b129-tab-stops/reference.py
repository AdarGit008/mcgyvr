"""Lay a report line's tab-separated pieces against a row of tab stops."""


def render_tabbed(line: str, stops: list) -> str:
    if not isinstance(line, str):
        raise ValueError("the line must be a string")
    if "\n" in line or "\r" in line:
        raise ValueError("the line must not span lines")

    def check_stops(raw):
        if not isinstance(raw, list):
            raise ValueError("stops must be a list")
        checked = []
        previous = 0
        for stop in raw:
            if not isinstance(stop, list) or len(stop) != 2:
                raise ValueError("a stop is a [column, kind] pair")
            column, kind = stop
            if isinstance(column, bool) or not isinstance(column, int) or column < 1:
                raise ValueError("a stop column must be a positive integer")
            if kind not in ("left", "right"):
                raise ValueError(f"unknown stop kind: {kind}")
            if column <= previous:
                raise ValueError("stop columns must strictly increase")
            previous = column
            checked.append((column, kind))
        return checked

    row = check_stops(stops)
    pieces = line.split("\t")
    laid = pieces[0]
    for piece in pieces[1:]:
        stop = None
        for candidate in row:
            if candidate[0] > len(laid):
                stop = candidate
                break
        if stop is None:
            laid = f"{laid} {piece}"
            continue
        column, kind = stop
        if kind == "left":
            laid = laid.ljust(column) + piece
            continue
        start = column - len(piece)
        if start <= len(laid):
            laid = f"{laid} {piece}"
        else:
            laid = laid.ljust(start) + piece
    return laid
