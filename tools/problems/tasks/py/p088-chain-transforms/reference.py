def chain_transforms(grid, steps):
    if not grid:
        raise ValueError("grid has no rows")
    width = len(grid[0])
    if any(len(row) != width for row in grid):
        raise ValueError("rows differ in length")
    current = [list(row) for row in grid]
    for step in steps:
        if step == "cw":
            current = [list(row) for row in zip(*current[::-1])]
        elif step == "ccw":
            current = [list(row) for row in zip(*current)][::-1]
        elif step == "mirror":
            current = [row[::-1] for row in current]
        elif step == "flip":
            current = current[::-1]
        elif step == "diag":
            current = [list(row) for row in zip(*current)]
        else:
            raise ValueError(f"unknown step {step!r}")
    return current
