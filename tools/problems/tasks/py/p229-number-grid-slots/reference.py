def number_grid_slots(rows: list) -> list:
    if not isinstance(rows, list) or not rows:
        raise ValueError("the rows must be a non-empty list")
    width = len(rows[0]) if isinstance(rows[0], str) else -1
    for row in rows:
        if not isinstance(row, str):
            raise ValueError("a row must be a string")
        if not row:
            raise ValueError("a row must not be empty")
        if len(row) != width:
            raise ValueError("the rows must be all of one length")
        for square in row:
            if square not in (".", "#"):
                raise ValueError("a square is either open or blocked")

    def is_open(row, col):
        return 0 <= row < len(rows) and 0 <= col < width and rows[row][col] == "."

    found = []
    count = 0
    for row in range(len(rows)):
        for col in range(width):
            if not is_open(row, col):
                continue
            across = 0
            if not is_open(row, col - 1):
                run = 0
                while is_open(row, col + run):
                    run += 1
                if run >= 2:
                    across = run
            down = 0
            if not is_open(row - 1, col):
                run = 0
                while is_open(row + run, col):
                    run += 1
                if run >= 2:
                    down = run
            if across == 0 and down == 0:
                continue
            count += 1
            found.append(
                {"at": count, "row": row, "col": col, "across": across, "down": down}
            )
    return found
