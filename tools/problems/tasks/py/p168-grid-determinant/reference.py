def grid_determinant(grid: list[list[int]]) -> int:
    if not isinstance(grid, list) or not grid:
        raise ValueError("grid_determinant expects a grid with at least one row")
    if len(grid) > 3:
        raise ValueError("a grid of four rows or more is out of range")
    for row in grid:
        if not isinstance(row, list) or len(row) != len(grid):
            raise ValueError("every row must be as long as the grid is tall")
        for cell in row:
            if isinstance(cell, bool) or not isinstance(cell, int):
                raise ValueError("every cell must be a whole number")
    if len(grid) == 1:
        return grid[0][0]
    if len(grid) == 2:
        return grid[0][0] * grid[1][1] - grid[0][1] * grid[1][0]
    total = 0
    for column in range(3):
        minor = [
            [cell for index, cell in enumerate(grid[row]) if index != column]
            for row in (1, 2)
        ]
        sign = 1 if column % 2 == 0 else -1
        total += (
            sign
            * grid[0][column]
            * (minor[0][0] * minor[1][1] - minor[0][1] * minor[1][0])
        )
    return total
