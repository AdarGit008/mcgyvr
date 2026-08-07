def lattice_route_count(grid):
    if not isinstance(grid, list) or not grid:
        raise ValueError("grid must be a non-empty list of rows")
    cols = len(grid[0]) if isinstance(grid[0], list) else 0
    for row in grid:
        if not isinstance(row, list) or len(row) != cols or cols == 0:
            raise ValueError("grid rows must be equal-length non-empty lists")
        for cell in row:
            if isinstance(cell, bool) or cell not in (0, 1):
                raise ValueError("cells must be 0 or 1")
    rows = len(grid)
    if grid[0][0] == 1 or grid[rows - 1][cols - 1] == 1:
        return 0
    routes = [[0] * cols for _ in range(rows)]
    routes[0][0] = 1
    for r in range(rows):
        for c in range(cols):
            if (r == 0 and c == 0) or grid[r][c] == 1:
                continue
            from_above = routes[r - 1][c] if r > 0 else 0
            from_left = routes[r][c - 1] if c > 0 else 0
            routes[r][c] = from_above + from_left
    return routes[rows - 1][cols - 1]
