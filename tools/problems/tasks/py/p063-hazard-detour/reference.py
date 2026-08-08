from collections import deque


def hazard_detour(grid, start, goal):
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
    for point in (start, goal):
        if (
            not isinstance(point, list)
            or len(point) != 2
            or not all(isinstance(v, int) and not isinstance(v, bool) for v in point)
            or not (0 <= point[0] < rows and 0 <= point[1] < cols)
        ):
            raise ValueError("start and goal must be in-bounds [row, column] pairs")

    def unsafe(r, c):
        if grid[r][c] == 1:
            return True
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ar, ac = r + dr, c + dc
            if 0 <= ar < rows and 0 <= ac < cols and grid[ar][ac] == 1:
                return True
        return False

    if unsafe(start[0], start[1]) or unsafe(goal[0], goal[1]):
        return -1
    if start == goal:
        return 0
    seen = {(start[0], start[1])}
    queue = deque([(start[0], start[1], 0)])
    while queue:
        r, c, steps = queue.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            if unsafe(nr, nc) or (nr, nc) in seen:
                continue
            if nr == goal[0] and nc == goal[1]:
                return steps + 1
            seen.add((nr, nc))
            queue.append((nr, nc, steps + 1))
    return -1
