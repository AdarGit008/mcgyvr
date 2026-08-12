def cell_name(row: int, column: int) -> str:
    return chr(ord("A") + column) + str(row + 1)


def grid_cells(rows: int, columns: int) -> list:
    names = []
    for row in range(rows):
        for column in range(columns):
            names.append(cell_name(row, column))
    return names
