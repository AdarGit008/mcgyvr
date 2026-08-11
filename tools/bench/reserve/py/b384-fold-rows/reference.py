def row_widest(grid: list) -> int:
    widest = 0
    for row in grid:
        if len(row) > widest:
            widest = len(row)
    return widest


def fold_rows(grid: list) -> list:
    """Every row padded out to the widest row's width."""
    if not grid:
        return []
    width = row_widest(grid)
    folded = []
    for row in grid:
        padded = list(row)
        while len(padded) < width:
            padded.append(0)
        folded.append(padded)
    return folded
