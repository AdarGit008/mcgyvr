def label_value_regions(grid: list[list[int]]) -> dict:
    if not isinstance(grid, list) or not grid:
        raise ValueError("the grid must hold at least one row")
    width = -1
    for row in grid:
        if not isinstance(row, list) or not row:
            raise ValueError("every row must be a list holding at least one square")
        if width == -1:
            width = len(row)
        if len(row) != width:
            raise ValueError("the rows are not all of one length")
        for square in row:
            if not isinstance(square, int) or isinstance(square, bool):
                raise ValueError("every square must be a whole number")
    height = len(grid)
    drawn = [[0] * width for _ in range(height)]
    sizes = []
    values = []
    nxt = 0
    for r in range(height):
        for c in range(width):
            if drawn[r][c] != 0:
                continue
            nxt += 1
            held = grid[r][c]
            count = 0
            pending = [(r, c)]
            drawn[r][c] = nxt
            while pending:
                row, col = pending.pop()
                count += 1
                for nr, nc in (
                    (row - 1, col),
                    (row + 1, col),
                    (row, col - 1),
                    (row, col + 1),
                ):
                    if nr < 0 or nr >= height or nc < 0 or nc >= width:
                        continue
                    if drawn[nr][nc] != 0:
                        continue
                    if grid[nr][nc] != held:
                        continue
                    drawn[nr][nc] = nxt
                    pending.append((nr, nc))
            sizes.append(count)
            values.append(held)
    return {"map": drawn, "sizes": sizes, "values": values}
