def count_trails(rows, cols, blocked):
    if not isinstance(rows, int) or not isinstance(cols, int) or min(rows, cols) < 1: raise ValueError("the floor is at least one cell by one cell")
    ropes = set()
    for cell in blocked:
        if not isinstance(cell, list) or len(cell) != 2: raise ValueError("a roped cell is a row and a column")
        if not (0 <= cell[0] < rows and 0 <= cell[1] < cols): raise ValueError("a roped cell lies off the floor")
        ropes.add((cell[0], cell[1]))
    if (0, 0) in ropes or (rows - 1, cols - 1) in ropes: raise ValueError("the entrance and the exit stay open")
    row = [0] * cols
    row[0] = 1
    for r in range(rows):
        for c in range(cols):
            if (r, c) in ropes: row[c] = 0
            elif c > 0: row[c] += row[c - 1]
    return row[cols - 1]
