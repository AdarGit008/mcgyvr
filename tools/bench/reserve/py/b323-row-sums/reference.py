def row_sums(grid: list) -> list:
    totals = []
    for row in grid:
        total = 0
        for value in row:
            total += value
        totals.append(total)
    return totals
