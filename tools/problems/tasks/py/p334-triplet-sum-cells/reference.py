MARK_LIMIT = 1000000000


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _read_sheet(sheet, rows, cols, into):
    if not isinstance(sheet, list):
        raise ValueError("a sheet must be a list")
    here = set()
    for entry in sheet:
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            raise ValueError("every entry must be a triple")
        row, col, mark = entry[0], entry[1], entry[2]
        if not _whole(row) or row < 0 or row >= rows:
            raise ValueError("a row index steps outside the shape")
        if not _whole(col) or col < 0 or col >= cols:
            raise ValueError("a column index steps outside the shape")
        if not _whole(mark) or abs(mark) > MARK_LIMIT:
            raise ValueError("a mark must be a whole number within the limit")
        if mark == 0:
            raise ValueError("a sheet may not carry a mark of nothing")
        cell = (row, col)
        if cell in here:
            raise ValueError("a sheet names the same cell twice")
        here.add(cell)
        into[cell] = into.get(cell, 0) + mark


def triplet_sum_cells(left: list, right: list, rows: int, cols: int) -> list:
    if not _whole(rows) or rows < 1 or rows > 10000:
        raise ValueError("rows must be a whole number from 1 through 10000")
    if not _whole(cols) or cols < 1 or cols > 10000:
        raise ValueError("cols must be a whole number from 1 through 10000")
    totals = {}
    _read_sheet(left, rows, cols, totals)
    _read_sheet(right, rows, cols, totals)
    out = [
        [row, col, mark] for (row, col), mark in totals.items() if mark != 0
    ]
    out.sort(key=lambda entry: (entry[0], entry[1]))
    return out
