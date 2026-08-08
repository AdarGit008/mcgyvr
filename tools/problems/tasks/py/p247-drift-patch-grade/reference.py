def grade_tolerant_patches(plate: list[list[int]], drift: int) -> dict:
    if not isinstance(plate, list) or not plate:
        raise ValueError("the plate must hold at least one line")
    if not isinstance(drift, int) or isinstance(drift, bool) or drift < 0:
        raise ValueError("the drift must be a whole number of zero or more")
    width = -1
    for line in plate:
        if not isinstance(line, list) or not line:
            raise ValueError("every line must be a list holding at least one cell")
        if width == -1:
            width = len(line)
        if len(line) != width:
            raise ValueError("the lines are not all of one length")
        for reading in line:
            if not isinstance(reading, int) or isinstance(reading, bool):
                raise ValueError("every reading must be a whole number")
    height = len(plate)
    seen = [[False] * width for _ in range(height)]
    found = []
    for r in range(height):
        for c in range(width):
            if seen[r][c]:
                continue
            seen[r][c] = True
            size = 0
            pending = [(r, c)]
            while pending:
                row, col = pending.pop()
                size += 1
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        nr = row + dr
                        nc = col + dc
                        if nr < 0 or nr >= height or nc < 0 or nc >= width:
                            continue
                        if seen[nr][nc]:
                            continue
                        if abs(plate[nr][nc] - plate[row][col]) > drift:
                            continue
                        seen[nr][nc] = True
                        pending.append((nr, nc))
            found.append((size, r * width + c))
    found.sort(key=lambda patch: (-patch[0], patch[1]))
    return {
        "count": len(found),
        "sizes": [patch[0] for patch in found],
        "seeds": [patch[1] for patch in found],
    }
