def region_totals(grid, queries):
    if not isinstance(grid, list) or not grid:
        raise ValueError("grid must be a non-empty list of rows")
    width = len(grid[0]) if isinstance(grid[0], list) else 0
    if width == 0:
        raise ValueError("rows must be non-empty lists")
    for row in grid:
        if not isinstance(row, list) or len(row) != width:
            raise ValueError("rows must all share one length")
        for cell in row:
            if isinstance(cell, bool) or not isinstance(cell, int):
                raise ValueError("cells must be integers")
    height = len(grid)
    prefix = [[0] * (width + 1) for _ in range(height + 1)]
    for r in range(height):
        for c in range(width):
            prefix[r + 1][c + 1] = (
                grid[r][c] + prefix[r][c + 1] + prefix[r + 1][c] - prefix[r][c]
            )
    totals = []
    for query in queries:
        if not isinstance(query, list) or len(query) != 4:
            raise ValueError("a query is [top, left, bottom, right]")
        for bound in query:
            if isinstance(bound, bool) or not isinstance(bound, int):
                raise ValueError("query bounds must be integers")
        top, left, bottom, right = query
        if top >= bottom or left >= right:
            raise ValueError("query bounds must name a non-empty block")
        if top < 0 or left < 0 or bottom > height or right > width:
            raise ValueError("query reaches outside the grid")
        totals.append(
            prefix[bottom][right]
            - prefix[top][right]
            - prefix[bottom][left]
            + prefix[top][left]
        )
    return totals
