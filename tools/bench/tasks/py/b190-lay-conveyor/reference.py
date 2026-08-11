"""Lay a straight eastward conveyor run across a factory floor plan."""


def lay_conveyor(floor, row, col, length):
    if row < 0 or row >= len(floor):
        raise ValueError("the run starts off the plan")
    cells = list(floor[row])
    if col < 0 or col + length > len(cells):
        raise ValueError("the run would pass the last column")
    for at in range(col, col + length):
        if cells[at] != ".":
            raise ValueError("the run covers a cell that is not open")
    for at in range(col, col + length):
        cells[at] = "="
    laid = list(floor)
    laid[row] = "".join(cells)
    return laid
