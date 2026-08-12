def cell_at(grid: list, row: int, column: int) -> int:
    if row < 0 or row >= len(grid):
        return 0
    if column < 0 or column >= len(grid[row]):
        return 0
    return grid[row][column]


def diag_of(grid: list) -> list:
    return [cell_at(grid, i, i) for i in range(len(grid))]
