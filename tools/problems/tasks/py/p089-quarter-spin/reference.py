def quarter_spin(grid, turns):
    result = [list(row) for row in grid]
    for _ in range(turns % 4):
        result = [list(row) for row in zip(*result[::-1])]
    return result
