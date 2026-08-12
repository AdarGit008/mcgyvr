def cell_count(grid: list, value: int) -> int:
    found = 0
    for row in grid:
        for cell in row:
            if cell == value:
                found += 1
    return found
