from collections import deque


def turn_cost_route(grid, step_cost, turn_cost):
    if not isinstance(grid, list) or not grid:
        raise ValueError("grid must be a non-empty list of rows")
    cols = len(grid[0]) if isinstance(grid[0], list) else 0
    for row in grid:
        if not isinstance(row, list) or len(row) != cols or cols == 0:
            raise ValueError("grid rows must be equal-length non-empty lists")
        for cell in row:
            if isinstance(cell, bool) or cell not in (0, 1):
                raise ValueError("cells must be 0 or 1")
    if isinstance(step_cost, bool) or not isinstance(step_cost, int) or step_cost < 1:
        raise ValueError("step cost must be a positive integer")
    if isinstance(turn_cost, bool) or not isinstance(turn_cost, int) or turn_cost < 0:
        raise ValueError("turn cost must be a non-negative integer")
    rows = len(grid)
    if grid[0][0] == 1 or grid[rows - 1][cols - 1] == 1:
        return -1
    if rows == 1 and cols == 1:
        return 0
    moves = ((-1, 0), (1, 0), (0, -1), (0, 1))
    dist = [[[None] * 4 for _ in range(cols)] for _ in range(rows)]
    queue = deque()
    for d, (dr, dc) in enumerate(moves):
        if 0 <= dr < rows and 0 <= dc < cols and grid[dr][dc] == 0:
            dist[dr][dc][d] = step_cost
            queue.append((dr, dc, d))
    while queue:
        r, c, d = queue.popleft()
        here = dist[r][c][d]
        for nd, (dr, dc) in enumerate(moves):
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols) or grid[nr][nc] == 1:
                continue
            cost = here + step_cost + (0 if nd == d else turn_cost)
            known = dist[nr][nc][nd]
            if known is None or cost < known:
                dist[nr][nc][nd] = cost
                queue.append((nr, nc, nd))
    best = [cost for cost in dist[rows - 1][cols - 1] if cost is not None]
    return min(best) if best else -1
