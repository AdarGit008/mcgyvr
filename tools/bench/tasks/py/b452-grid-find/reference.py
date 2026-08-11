def match_at(grid: list, row: int, column: int, value: int) -> bool:
    return grid[row][column] == value


def grid_find(grid: list, value: int) -> list:
    for r in range(len(grid)):
        for c in range(len(grid[r])):
            if match_at(grid, r, c, value):
                return [r, c]
    raise ValueError("the value is not in the grid")
