def grid_flip(grid: list) -> list:
    if not grid:
        return []
    flipped = []
    for column in range(len(grid[0])):
        flipped.append([row[column] for row in grid])
    return flipped
