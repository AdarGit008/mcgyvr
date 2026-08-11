def col_sum(grid: list, column: int) -> int:
    total = 0
    for row in grid:
        if column < len(row):
            total += row[column]
    return total
